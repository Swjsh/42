## [2026-06-19] CONTEXT-116: GEX->premarket wiring spec (propose-only, commit 01d0695)

Closed a partial-visibility gap: gex_capture.py banks gex-regime.json daily but NOTHING consumed it. docs/GEX-PREMARKET-WIRING.md = the exact copy-pasteable premarket.md edit (Reads + new Step 3c intake + today-bias gex_context field) carrying the dealer-gamma regime -> heartbeat -> classify_regime(gex_hint). Consumer interface ALREADY existed + is conservative (reinforce-only: nudges NEUTRAL base, never flips a directional read). Mapping: short_gamma_trend=trend/continuation-friendly (edge regime); long_gamma_pin=pin/fade+size-down+respect walls. VERIFIED end-to-end on live tag (label in vocab; long_gamma_pin+low-VIX->range_pin; strong-BULL+pin stays bull_trend). Additive-only today (book WATCH_ONLY=no trade changes); ready on promotion. NOT applied (Rule 9); apply-gate = >=5 banked days + label sanity check, after-hours. No engine/prompt/params touched.

---

## [2026-06-19] CONTEXT-115: DATA RULES — 313 real winners journaled -> automation ground truth + principled sizing study (commits a3cda6c, a0cd64e)

J: "data rules ... take the winners, journal properly, turn into automation." Built the full pipeline + answered his 2 open sizing decisions with HIS numbers.

**Data-rules pipeline (a3cda6c):** 313 Webull WINNERS (+$37,974; 294 are 1-2 lot = his real edge) journaled in the canonical 43-col schema -> journal/j-real-winners.csv (dedicated file, account_id=j_webull_hist, never pollutes live trades.csv) + digest, each w/ SPY-5m-reconstructed setup context. Signature: balanced 51%C/49%P, morning-heavy, VWAP-aligned; archetypes momentum-breakout 41% / pullback-cont 26% / reversal 19% / trend-cont 14%. Two-tier ground truth (docs/J-EDGE-GROUND-TRUTH.md): in-era 2026 anchors gate the backtest, the 313 winners DEFINE/parameterize the specs (era-gapped, honest). His 4 archetypes map onto EXISTING regime_book setups (docs/J-EDGE-SETUP-SPECS.md) — no new machinery, just parameters from his data. Caught+fixed a DST tz bug (C6).

**Principled sizing study (a0cd64e) — answers J's 2 decisions:** L168 quantified on the full 1,182-round-trip ledger. Cliff: 1-2 lots +$436 (47%WR; flat-only +$4,294) | 3-5 lots -$17,322 (23%WR) | 6+ -$4,663. UNTANGLE: it is BOTH — scaling-in catastrophic at every size (75 trades -$18,912) AND flat-3+ also negative (-$6,930, confounded w/ revenge so not conclusive). Revenge real (post-loss trades -$11,304). Half-Kelly = ~2 contracts; conservative-binary Kelly NEGATIVE (edge exists only because he cuts losers). DECISIONS: (a) KEEP MIN-3 — damage is ABOVE the floor not the floor; real lever = a premium ceiling ~6% equity (tension flagged: flat-3 data IS negative but confounded). (b) ADD post-loss throttle — highest-value sizing change; DESIGN only (pure post_loss_qty_ceiling, fail-closed, order-only/never locks human). Both propose-only (Rule 9), risk_gate+params byte-untouched, gym 87/87.

---

## [2026-06-19] CONTEXT-114: DIVERSIFICATION — the edge family is PULLBACK/TREND-CONTINUATION (both directions)

Answering J's "more than bearish rejection." Mined J's real Webull history + discovered edges from candles. CONVERGENT finding across BOTH: the transferable 0DTE edge is the PULLBACK / TREND-CONTINUATION family, BOTH directions — while reversal-fades + mean-reversion-bounces consistently DIE (C3: 0DTE theta destroys mechanical fades).

**3 data-discovered WATCH candidates now in regime_book.py (inert, WATCH_ONLY):**
- VWAP_TREND_PULLBACK (H4): +$45-63/trade, both dirs, DSR PASS, OOS-stable, survives drop-top5.
- GAP_AND_GO (H2b): +$35-40/trade, 5/6 quarters +, both dirs.
- MA_PULLBACK_RESUMPTION (A2, ITM1): +$11.81, all 6 quarters +, both dirs (fires ~100% days = trend overlay, C27).
All proxy-level, need real ★★★ + promotion-gate before live.

**J's real edge (Webull 2021-23, 667 trades):** pullback/reversal trader, better long, winners cluster midday, every winner correct side of VWAP. #1 finding = SIZING (1-2 lots +$4,576 / 3+ lots -$17,461; sizes UP into worst trades) -> L168.

**2 DECISIONS FOR J (Rule 9, surfaced not resolved):** (a) doctrine min-3 contracts vs J's 3+ losing band - is flat-3 ok (the killer is sizing-UP/adding, not flat-3)? (b) add a post-loss size throttle to risk_gate (currently only static per-trade cap, no equity-trajectory throttle)?

**Conclusive negatives:** reversal-off-VWAP-extreme (loser both dirs), midday-mechanical-overlay (not actionable - J's time edge was discretionary), intraday-momentum standalone, ORB+RVOL. Edge = pullback/continuation, not reversal/mean-reversion.

---

## [2026-06-19] CONTEXT-113: DIVERSIFIED BOOK — bias corrected, regime-aware multi-setup framework built

J: "we need more than just bearish rejection." Correct + my prior "only bearish" was a FRAMEWORK ARTIFACT (everything gated on edge_capture vs 3 BEARISH anchors). Unbiased standalone real-fills re-eval (fleet-standalone-regime.json):
- BEARISH_REJECTION standalone = -\$29.52/trade (6th of 7); kept ONLY by its bearish-anchor edge_capture.
- 3 setups POSITIVE standalone: DOUBLE_BOTTOM_MORNING_LOW_VOL +\$20 (OOS-stable, best), BULLISH_RECLAIM +\$10 (up-day #2), DOUBLE_BOTTOM_BASE_QUIET +\$6. Bias had BURIED NAMED_LEVEL_SECOND_TEST long leg (+\$2.81/62%WR/n=257).
- Regime->setup map: bull_trend->BULLISH_RECLAIM/DOUBLE_BOTTOM; bear_trend->BEARISH_REJECTION+NAMED_LEVEL long; high_vol->NAMED_LEVEL; range_pin->(bounce family may revive on real levels, n too thin now); neutral->abstain.

BUILT (propose-only, INERT): docs/REGIME-AWARE-BOOK.md + backtest/lib/engine/regime_book.py (classify_regime + REGIME_SETUP_MAP data + select_setups; 33 tests) + a promotion lifecycle (WATCH_ONLY -> REGIME_ACTIVE: real ★★★ standalone-positive + OOS + DSR>=0.90 + J per-setup winner + A/B). select_setups returns () for ALL regimes today (entire map WATCH_ONLY) = ships without changing a trade. The framework is wired; setups slot in as they earn it.

THE 2 UNBLOCKS (highest leverage): (1) real ★★★ levels (archive accruing - re-run in-regime eval once ~20-30 days bank; proxy verdicts may flip) + (2) J's own WINNING EXAMPLES per non-bearish setup (we have anchors for bearish only - bullish/double-bottom/reversion winners would let those validate on their merits). All candidates WATCH-level (proxy/weak-DSR) - not tradeable yet. gym 87/87.

---

## [2026-06-19] CONTEXT-112: WEEKEND RESEARCH LOOP — 3 ratification candidates + conclusive negatives (commits c1a5e48..eee84e9)

Autonomous weekend research (continuous loop, ~12 research/validation cycles, propose-only Rule 9). Converged the entry space + deepened the one confirmed edge. Ratification package: docs/WEEKEND-FINDINGS-RATIFICATION-2026-06-19.md.

**READY TO RATIFY (OOS-validated):** (1) chandelier trail 20%->15% (6/6 WF folds, broad-based, pending real-level anchor check); (2) confidence-tier fix - STOP sizing up on HIGH (was sizing up on its WORST trades, ~\$700 worse than flat; corrected VIX-character tier +\$3.2k vs flat, ATM); (3) VIX-falling=SKIP (do-no-harm, sign-stable). All Safe-account; Bold takes conservative halves only (C29).

**CONCLUSIVELY RULED OUT:** bounce family (dead), new entries trendline/momentum/vwap (all anti-edge - BEARISH_REJECTION is the ONLY edge-aligned entry), morning-sign gate (look-ahead mirage L166), lunch gate (L167), theta-cliff exit (C28), vol-scaled chandelier (inverts on 0DTE).

**UNBLOCKED:** ★★★ key-levels archive (the #1 data constraint - now accruing; re-run level validations once N>=20-30 real days bank - proxy RETIRE verdicts + #1's anchor check may change). GEX regime tag built (live going-forward, no historical chain OI to backtest).

**THE WALL + THE TRUTH:** BEARISH_REJECTION is the edge; leverage is exit/regime on it (the 3 wins). The setup is real-fills-NEGATIVE on PROXY levels but J's real winners were on real ★★★ levels the proxies miss -> resolving the level-quality gap (the archive) is the highest-value path. Real validation resumes Monday with live data + accruing archive.

---

## [2026-06-19] CONTEXT-111: ALL-NIGHT LOOP TERMINUS (reasoned, non-silent) — 15 commits

Phase 3 shim (engine_cli.py) shipped — the decision-lib boundary the heartbeat will consult in Phase 4. That EXHAUSTS the bounded high-value backlog. Everything remaining (forward-backlog-2026-06-19.md) is now DELIBERATE-FUTURE / J-GATED / CALENDAR-BOUND: Phase 3 SHADOW needs >=5 live trading days (market closed through Mon); Phase 4 cutover is J-gated; BEARISH_REJECTION exit/regime research is meaty + blocked by the proxy-levels caveat; key-levels archive only accrues real levels going forward; watcher RETIRE needs J. Per OP-22 (good-enough is a valid terminal state; only SILENT stops are banned) + J's #1 constraint (not over-engineered), force-grinding deliberate-future architecture at 03:30 would be the wrong call. WRAPPING the overnight grind here — loop resumes via the conductor (when J enables it) or Monday's session on the queued forward work. Tonight: 15 commits 5d247c6..<engine_cli>, gym green throughout, live trading untouched bar the validated Safe chart-stops (Monday).

---

## [2026-06-19] CONTEXT-110: ALL-NIGHT AUTONOMOUS LOOP COMPLETE (16 commits 5d247c6..22988b0)

J: "work all night, find things, fix, improve, Gamma fully autonomous professional trader learning + improving." Ran the conductor loop manually: maintained a tracked backlog, worked the highest-value bounded task each cycle, verified (gym green) + committed each, paced through a peak-load 529 window. 6 cycles after the blueprint Waves A-D.

**Completed + committed (backlog #16-26):** queue triage (172 stale CRITICALs archived); CONTEXT-109 loose ends (params mojibake, slow-test hook split, frontmatter YAML); decision-lib Phase 1 (engine/score.py) + Phase 2 (engine/gates.py) extracted + parity-locked (assert-agree, backtest byte-identical); lessons->guards (L164/L165 + verify_committed/tz-localize/profit-lock guards; CAUGHT+FIXED a live tz bug in safe_trendline_spread_gate.py); promotion-rigor (DSR/PBO) wired into scorecards; Gamma operator persona (gamma.md coherent identity, 310->159 lines); account_id stamped at the ledger writer; op11 stale test fixed.

**Strategic findings (the research payoff):** (1) the mean-reversion BOUNCE family (floor_hold, close_ceiling, named_level_second_test) is DEAD/anti-edge under every tested exit/regime/short-inversion (watcher-exit-sweep.json, bounce-family-rescue.json) -> RETIRE. (2) BEARISH_REJECTION is THE edge — the only entry firing WITH J on real fills (bearish-continuation-family.json). (3) The leverage is EXIT/REGIME refinement of the confirmed setup, NOT new entries. Focus engineering there.

**Durability lesson (L164):** `git commit --only` silently drops UNTRACKED new files — several Wave B deliverables (risk_gate.py etc.) were never committed until caught + fixed (bd52457). Now guarded by setup/scripts/verify_committed.py. Always `git add` new files before --only.

**Forward backlog (deliberate-future, NOT 2am-grind):** automation/overnight/forward-backlog-2026-06-19.md — Tier 0: BEARISH_REJECTION exit/regime refinement. Tier 1: decision-lib Phase 3 (engine_cli shim + shadow) + Phase 4 (cutover, J-gated). Tier 2: production key-levels archive; watcher-fleet RETIRE (J approves).

---

## [2026-06-18] CONTEXT-109: BLUEPRINT EXECUTED — 4 waves, professional restructuring (commits 5d247c6, effa672, 26775b1 + spec)

J: "I want all of it, make it not over-engineered and professionally structured, work through the entire plan tonight methodically." Executed the GAMMA-AUTONOMY-BLUEPRINT in 4 ordered waves, verification-gated + committed after each. Final gym 88/88 WITH replay. ~30 agents across the night.

**Wave A — foundation + de-sprawl (5d247c6):** engine health beacon (engine-health.json, market-hours aware, Discord RED transition-alerts); Pydantic state contracts (load_validated at every read — caught real decisions.jsonl corruption); watcher registry + reconciliation test (orphan bug now impossible; count 28->25, deleted SNIPER+pinfade); validator/task/params-drift tests (caught 2 undocumented tasks). De-sprawl: archived 215 files / ~2.6MB (candidates 527->348).

**Wave B — risk + efficiency (effa672):** risk_gate.py (ONE pure check_order, fail-closed on unreadable input, never locks out J — proven; 66 tests; orchestrator assert-agree); per-agent model routing (chef/gamma->opus, pilot/analyst/treasurer->sonnet, 5 rote->haiku; was all-Sonnet); promotion rigor (DSR/PBO/CSCV, advisory); canonical ledger writer (append_decision).

**Wave C — autonomy + doctrine (26775b1):** conductor.md (Ralph-loop, opus, 4 safety rails: after-hours/fail-open/one-task/propose-not-auto-apply) + Discord approve/revoke bus — BOTH wired, NOT auto-enabled (J runs install-conductor-task.ps1 / install-discord-responder-task.ps1 to enable). **CHART-STOPS doctrine: validated real-fills A/B -> SHIPPED on Safe** (WR 38%->65%, P&L $8,160->$16,671, edge_capture invariant, DSR PASS; premium stop demoted to -50% catastrophe cap, chart-stop now primary) **-> NO-SHIP on Bold** (regresses; ITM-2+5x economics need the tight stop; unchanged). Heartbeat hygiene: canonical ledger schema, watcher count fix, pre_order_gate delegates to risk_gate.

**Wave D — spec the deep refactor:** docs/SHARED-DECISION-LIBRARY-MIGRATION.md — the one remaining big piece (unify params<->heartbeat<->filters into ONE library both backtest+live use). ~80% of detector->Insight already exists (WatcherSignal+registry); remaining = extract scoring->gates->shadow->cutover, mirroring the risk_gate precedent. Honest 3-4wk estimate (shadow window is calendar-bound). 11 conductor-sized tasks.

### LIVE CHANGE TAKING EFFECT MONDAY 2026-06-22 (review):
- **Safe chart-stops:** premium_stop_pct -0.08/-0.10 -> -0.50 (catastrophe cap); chart-stop primary. Revert: docs/CHART-STOPS-2026-06-18.md. Bold unchanged.

### To ENABLE when ready (wired, off):
- Gamma_HealthBeacon (install-engine-health.ps1), Gamma_Conductor (install-conductor-task.ps1), Gamma_DiscordResponder (install-discord-responder-task.ps1).

### Loose ends flagged (non-blocking):
- Legacy decisions.jsonl data still corrupt (immutable; producers fixed going-forward).
- params.json has cp1252 mojibake bytes in a _doc field (contracts loader handles via utf-8-sig; plain json.load fails — worth a clean re-save).
- Per-edit pytest hook runs the >600s graduated-guards suite and false-blocks unrelated edits — split fast/slow guards.
- Agent frontmatter has unquoted-colon descriptions (latent strict-YAML foot-gun).

---

## [2026-06-18] CONTEXT-108: DECISION-LEDGER corruption fixed at the PRODUCER level (WRITE side)

The state-contract test surfaced `decisions.jsonl` (56/122 rows corrupt) and `aggressive/decisions.jsonl` (168/427 corrupt). Root cause = multiple competing producers writing INCOMPATIBLE formats into the same append-only file: pretty-printed multi-line `json.dump(...indent=2)` (the `'Field required'` fragments in the safe ledger), concatenated objects on one physical line with no trailing `\n` (the `'Extra data'`/`'Expecting property name'` rows in the aggressive ledger), and schema drift (`bear_score` vs `bearish_score`, `action` vs `decision`, missing `tick_id`/`date`, literal-string `"position_status":"null"`). Existing rows are IMMUTABLE (untouched); this fixes the WRITERS so every NEW row is clean. Complements the earlier kitchen_daemon `errors='replace'` READ-side fix.

**Canonical writer shipped:** `backtest/lib/ledger.py#append_decision(path, row)` — validates the row against `DecisionRowModel`, serializes compact single-line (`json.dumps(..., separators=(",",":"))`) + `"\n"`, appends utf-8 + flush. One row → one line → always valid, or it raises `StateContractError` and writes NOTHING (fail-closed; a malformed row never reaches disk). Test: `backtest/tests/test_ledger_writer.py` (4 passed) proves clean-write + fail-loud-on-invalid + no-partial-append-on-existing-ledger.

**Canonical schema PINNED:** `action` (NOT `decision`), `bull_score`/`bear_score` (NOT `bearish_score`), required `tick_id`+`date`+`action`. Chosen because the MAJORITY of consumers already index these names: both heartbeat.md templates, `eod_deep/main.py` (CONTEXT-106 fixed it FROM `d["decision"]` TO `d["action"]` — confirming the pin), `pattern_backtest.py`, `near_miss_audit.py`, `shadow_model_eval.py`. = `DecisionRowModel` as it already stood; the writer just enforces it at the boundary.

**Python producer repointed:** `setup/scripts/backfill_decisions.py` (the only Python writer of the canonical `decisions.jsonl`) now calls `append_decision` instead of its ad-hoc `open('a')`+`json.dumps`. Imports verified, py_compile clean, state-contract test still 16/16 green (findings unchanged — no existing data mutated).

**Satellite ledgers intentionally NOT forced through `DecisionRowModel`** (they are DIFFERENT artifacts, not the corrupted canonical ledger, and are already single-line + newline-terminated): `fast-path-decisions.jsonl` (`fast_path_executor.py` — its rows use `decision`/`account`/`decided_at_utc`/`placed`; it reads its OWN ledger back expecting `rec.get("decision")` at L408, so forcing `action`/`tick_id`/`date` would break it) and `shadow-model-decisions.jsonl` (`shadow_model_eval.py` — comparison-scorecard rows with `real_action`/`shadow_action`, not a decision row). Forcing either through the decision contract would REJECT their valid rows — a correctness regression, not a fix.

> **NOTE FOR THE HEARTBEAT-OWNING WAVE (heartbeat.md + aggressive/heartbeat.md — NOT edited here):** the heartbeat PROMPT is the PRIMARY writer of the canonical `decisions.jsonl` (the LLM emits the JSON line literally per the prose template), and is therefore the remaining source of NEW multi-line / concatenated / key-reordered / `"null"`-string drift. When that wave touches the prompt, pin the emitted row to the canonical schema: **single compact line, no trailing-object concatenation, keys `tick_id`(int) + `date`(str) + `action`(str) REQUIRED, scores as `bull_score`/`bear_score`, `position_status` a real JSON `null` (not the string `"null"`)**. Match exactly the shape `append_decision` validates (`DecisionRowModel`). Ideally route the prompt's write through a tiny Python shim that calls `append_decision` so the LLM never hand-serializes JSON. Until then, the writer + contract guard the Python producers; the prompt remains the one un-guarded writer.

---

## [2026-06-18] CONTEXT-107: FIX-ALL + E2E VALIDATION COMPLETE (committed 244b9e5)

J directive: "fix all your findings then validate the engine end to end ... go nuts." Two more waves on top of CONTEXT-106. ALL deferred findings fixed + full E2E validation (16 agents total across the night).

**Deferred findings — ALL fixed:** analyst->chef handoff (eod_fallback.py deterministic cook-queue append, no Write tool needed) + repaired a cook-queue.jsonl UTF-8 corruption byte crashing the daemon read at task 834/2751 (it saw 1/3 of its own queue); kitchen_daemon utf-8 errors=replace + line-resilient; **stairstep_continuation RETIRED** (every variant anti-J-edge — negative real-fills AND edge_capture, profits on J loss days; fabricated v45 fixture replaced with real 5/07 tape asserting non-fire); shadow 8c repointed to shadow-model-decisions.jsonl real schema; account_id default-by-file in consumers; stray backtest/crypto/__init__.py deleted; news.json as_of; breaker schema documented.

**E2E validation — surfaced + fixed NEW instances of the class:** premarket now writes safe_equity_confirmed/bold_equity (strike-tier primary input had no producer); eod-summary repointed off retired params_safe/bold.json (dual-account kill-switch reporting was going dark); **orchestrator.py: vix_bear_hard_cap + entry_bar_body_pct_min were DEAD via the params_overrides path** (any A/B loading them from params ran WITHOUT them) — now assigned + in runner passthrough + regression-guarded; heartbeat watcher schema guard for malformed/foreign rows; run_dual_account/j_winner_audit retired-path refs.

**Validation result:** gym 88/88 WITH replay; v25 presence guard adversarially proven (catches phantom gate); backtest reproducible (identical run_id); all 6 live gates fire via BOTH kwarg + params paths; watcher feed proven live (2 obs, 0 errored, level-keyed watchers see real levels); both broker accounts (Safe PA3S2PYAS2WQ $2K, Bold PA33W2KUAT40 $1649) + TV chart (BATS:SPY 5m + Saty ribbon) connectivity confirmed; options L3 both.

### Two doctrine questions for J (NOT changed — Rule 9, need your ruling):
1. **Bold kill-switch threshold:** aggressive/circuit-breaker.json loss_pct trips at **-60%**, but CLAUDE.md Rule 5 + aggressive/params.json#daily_loss_kill_switch_pct say **-50%**. Which is canonical?
2. **Bold strike offset:** aggressive/params.json#strike_offset_itm: 2 matches Safe's; run_dual_account.py docstring claims Safe=ATM/Bold=ITM-2. Likely a stale docstring (per-tier selection happens in heartbeat) — verify intended.

### Verify Monday 2026-06-22 (Fri 06-19 = Juneteenth, market CLOSED):
- premarket writes day_trades_used_5d + safe_equity_confirmed/bold_equity (today's were pre-fix).
- watcher-observations.jsonl populates with the live date (inert-feed fix's first live session is Monday).

---

﻿## [2026-06-18] CONTEXT-106: BULLETPROOFING PASS — partial-visibility bug class hunted + fixed (committed 5da0da2)

J directive: "fix all 4 phases... look for any other loose ends like this... where one item only sees portions of others... review it all... bulletproof." Adversarial re-verification of tonight's watcher work + 4-front audit of the producer/consumer-contract bug class (a CONSUMER silently seeing a SUBSET, often zero, of what a PRODUCER emits). 8 agents. Committed durably (5da0da2) so an overnight state-restore can't silently revert live-trading fixes.

**FIXED — CRITICAL:**
- Retired stale `params_safe/bold.json` (frozen May 14) + `heartbeat.md` is now SAFE-ONLY. Removes an armed footgun: the Safe task could place Bold orders on a stale -15% stop vs the real -7%.
- Ported 6 params-active gates into the live heartbeats (they were in `params.json`+`orchestrator.py` but NOT the live prompt — live was not applying what params said). Now live==params for BOTH accounts, consistent with CONTEXT-105: AGG correctly did NOT receive `block_level_rejection` (removed there); SAFE received all 6 (SAFE decision = keep-all). **Value nuance:** `block_level_rejection` is IS +$13,181 but OOS/WF marginal (SAFE 1/6, -104, flagged REVIEW); `vix_bear_hard_cap` OOS barely +30 (kept for regime protection). Both are now live-consistent-with-params; if the pending 4-way A/B flips them false, the new v25 guard FORCES the heartbeat to follow.
- `watcher_live.py` wrote ZERO observations all day (CSV-timing bug) → tonight's unified watcher layer was reading a feed frozen at 06-15 (INERT). Fixed: yfinance fallback when the rolling CSV is absent + all silent-return paths now log. **VERIFY TOMORROW AM:** confirm `watcher-observations.jsonl` populates with today's date.

**FIXED — HIGH (field-name / handoff contract):** strike-tier + PDT + equity reads keyed on `account_equity`/`start_equity`/`day_trades_used_5d` that no producer wrote (premarket now writes them); `eod_deep/main.py` keyed on `d["decision"]` while producer writes `d["action"]` (dropped every engine decision); `WATCH_ONLY` had zero consumers → added to eod-summary + weekly-review + dashboard.

**GRADUATED GUARD (prevents recurrence, OP-25):** `v25_filter_gates.py` presence assertion — every active gate knob in BOTH params files must be grep-referenced in its heartbeat or the gym FAILS. Now covers the aggressive account. 47/47; gym 87/87 green.

### Known broken / deferred (cook-queue tasks filed):
- **stairstep_continuation**: fires on FABRICATED bar values (docstring + v45 gym fixture are NOT the real 5/07 tape) AND is anti-J-edge (5/07 is a J LOSS day; every tested logic fix worsened edge_capture). WATCH_ONLY, **DO NOT PROMOTE** — needs eval-first/J redesign.
- **analyst→chef handoff doubly broken**: free-tier analyst has no Write tool (skips chef-inbox) AND `kitchen_daemon` reads `cook-queue.jsonl`, never `_chef-inbox/`. Reflection→R&D routing silently dropped most days.
- **account_id absent on ~90% of decisions.jsonl rows** — now load-bearing (WATCH_ONLY consumers + shadow group by account).
- **shadow auto-ratify contract mismatch**: eod-summary 8c reads `decisions.jsonl`+`version`/`would_have_action`; shadow writes `shadow-model-decisions.jsonl`+`real_action`/`shadow_action` (latent — shadow disabled, but the 5-of-7 auto-ratify would never advance once enabled).
- stray 0-byte `backtest/crypto/__init__.py` shadows the real `crypto` pkg (pattern_backtest self-heals; delete the file for the clean root fix); cross-account circuit-breaker schemas divergent (C9); `news.json` staleness reads wrong key (cosmetic); dashboard watcher panel deferred (color-map fix shipped).
- **Audit caveat:** even the audit agents had partial visibility — the gate-audit agent cited a stale scorecard and didn't read CONTEXT-105's WF conclusions. Cross-checked here.

---

## [2026-06-18] CONTEXT-105: WF VALIDATION COMPLETE — 2 AGG GATES REMOVED, SAFE ISSUES FLAGGED

**AGG WF complete (7 gates, 6 folds) — 2 gates auto-ratified for removal:**

| Gate | WF OOS passes | Total OOS delta | Action |
|---|---|---|---|
| midday_trendline_gate | 0/6 | -2,996 | REMOVED — superseded by require_bearish_fill_bar (C15) |
| block_conf_lvl_rej_midday_afo | 0/6 | -562 | REMOVED — never helped OOS when fired; fill_bar changed composition |
| block_conf_lvl_rec_afternoon | 0/6 | +0 | KEPT (dead code, $0 impact) |
| block_level_rejection | 1/6 | -693 | REMOVED — 4-way A/B in 5-gate context: IS+45(n_chg=0), OOS+500(+1 bear winner), all 5 OP-22 gates pass |
| block_elite_bull | 3/6 | -79 | STABLE enough — keep (bull-side, unaffected by fill_bar) |
| require_bearish_fill_bar | 5/6 | +1,975 | STABLE ✓ — dominant bear filter, supersedes all bear blockers |
| block_bull_morning_agg | 4/6 | +484 | STABLE ✓ |

**AGG FINAL state (3 gates removed: midday_trendline + conf_lvl_rej + level_rejection):** IS n=215 pnl=+$9,780 WR=39.5% | OOS n=25 pnl=+$1,853 WR=68.0% (was 7-gate: IS n=129 +$4,164 31.0%, OOS n=18 +$1,205 55.6%). Combined delta: IS=+$5,616 n_chg=+86, OOS=+$648 n_chg=+7. **C15 key finding: require_bearish_fill_bar supersedes ALL bear-blocking gates — 3 redundant gates cleaned up.** Active gates: require_bearish_fill_bar (bears) + block_elite_bull + block_bull_morning_agg (bulls). Scorecard: analysis/recommendations/agg_wf_gate_removal_2026_06_18.json.

**SAFE WF complete (8 gates, 6 folds) — no changes, 3 items flagged:**

| Gate | WF OOS passes | Total OOS delta | Action |
|---|---|---|---|
| midday_trendline_gate | 4/6 | +241 | STABLE ✓ — KEEP (no fill_bar gate in SAFE) |
| block_elite_bull | 6/6 | +897 | STABLE ✓ — strongest SAFE gate |
| entry_bar_body_pct_min_0.20 | 4/6 | +215 | STABLE ✓ — negative IS but OOS real |
| block_bull_1100_1200 | 3/6 | +140 | BORDERLINE — keep |
| vix_bear_hard_cap_23 | 1/6 | +30 | REVIEW — IS cost -5763, OOS barely +30; keep for regime protection |
| block_level_rejection | 1/6 | -104 | REVIEW — same pattern as AGG |
| block_conf_lvl_rec_afternoon | 2/6 | -671 | FLAG — IS goes negative fold5; needs 4-way A/B |
| min_triggers_bull_2 | 2/6 | -714 | FLAG URGENT — fold6 OOS=-799 (1-trigger bulls now winning in May-Jun 2026); needs 4-way A/B |

**SAFE 4-way A/B results:** `min_triggers_bull_2` G1 FAIL (IS_delta=-$662) — KEEP min_triggers=2 despite OOS+$799 (all 6 new OOS bull trades win). Regime change confirmed: 1-trigger SAFE bulls win in May-Jun 2026 but are IS losers → needs VIX-regime classifier before unlock. `block_conf_lvl_rec_afternoon` G2 FAIL (OOS_delta=-$81) — KEEP. Both SAFE gates correct as-is. **SAFE unchanged.**

---


---

> **Older entries (CONTEXT-104 and earlier) archived** to [STATUS-ARCHIVE.md](STATUS-ARCHIVE.md) on 2026-06-19 (OP-22 consolidation — kept STATUS.md lean so each wake does not load ~160K tokens). This file holds the current arc only.

- [2026-06-19 10:57:15] crypto-harness drift RED :: stage v02_source_parity pass rate dropped to 94.0% in last 24h (94/100) -- but v15 (3-source) = 100.0% in same window, likely single-provider artifact :: see crypto/data/scorecards/drift_report.json

# FABLE GAP AUDIT — 2026-07-07 (post-marathon review: the unknown unknowns)

> **Written by Fable at J's request ("see the gaps, inform us") with J at 95% Fable usage — this doc IS the handoff.**
> Every item: WHAT / EVIDENCE / WHY / EXACT NEXT ACTION, ranked by trading impact. Opus executes top-down without needing me.
> Rule for the executor: each item below is a CLAIM with a pointer — re-verify the pointer before building (this repo's disease is inherited claims).

---

## THE THREE REFRAMES (read these before the list)

### R1 — The 2026 OOS window is BURNED. Forward paper is the only virgin holdout left — and the fleet is the forward-validation machine nobody is using.
Tonight ran ~130+ configs across ~10 batteries (exit-grid 8, hold 6, selective 4, spread 9, confluence 42, dynamic-stop 42, DTE ladder, walk-forward, vwap A/B) — **all reading the same 2026-H1 "OOS" window**. Each battery FDR'd *internally*; **nothing corrected across batteries**, and battery N's design was chosen after reading battery N-1's OOS. That's a garden of forking paths: the 2026 window is now selection surface, not a holdout.
**Consequences:** (a) tonight's ships (vwap exit −0.06/0.40) stand on their gates but their true test is **forward fills** — the fill-funnel/EOD digest is the real scorecard now; (b) any FUTURE arming decision on these signal families needs forward paper evidence or genuinely new data (post-2026-07 OPRA), not another read of the same window.
**The unlock nobody stated:** the 6-account fleet IS the forward-OOS farm. Divergent arms trading different profiles on the same days = parallel live samples = the honest re-test for every HOLD-verdict candidate. The 2DTE HOLD (sizing floor at $2K) is *unarmable on Safe-2* but **paper equity is arbitrary** — a dedicated forward-test arm with adequate paper funding can run 2DTE forward TODAY. Tonight's HOLD becomes a running experiment instead of a shelf item.
**Action:** create `analysis/backtests/holdout-ledger.json` (window → experiments that read it → burned status); lesson-inbox a C4-family entry ("cross-battery multiplicity — the night that read OOS 130 times"); route HOLD candidates to forward arms (see G4).

### R2 — Tonight's code meets its first live open tomorrow 09:30. It has never seen a market open.
Five audit fixes + a new exit shape + adoption logic went into the production tick tonight. All guarded, all green — **in test harnesses**. The specific pre-open risks are G1–G3 below. Do them before 09:30 or accept unverified-at-open risk consciously.

### R3 — Stop running batteries at J's discretionary edge. Capture it instead.
Six kills tonight all say the same thing: J's edge (regime direction, timed at levels, same-day) is real but **not mechanizable from 7 anchor trades**. The binding constraint is *n*, not lens count. The J-call corpus is ~7 trades from May + today's put. Every battery burns the same tiny anchor set; meanwhile J's live calls — the actual ground truth — evaporate into chat logs. **Build the capture loop, not another battery** (G5). n grows → mechanization becomes possible later; alerts + execution capture value NOW.

---

## TIER 1 — BEFORE TOMORROW'S OPEN (money-path safety)

### G1 — Adopted-position exit shape is UNSPECIFIED (FIX1 blast radius). ⚠️ highest immediate risk
**What:** FIX1 makes the engine ADOPT any untracked open position into the exit_manager. But `register_entry` requires an `exit_shape` — **which shape does an adopted manual position get?** The workflow result never says. Adoption fires inside `_execute` (i.e., on the engine's next ENTER attempt), so the shape may come from *whatever verdict happened to fire* — meaning J's manual put could be auto-sold at some setup's TP1/stop that J never chose. J's revealed preference (he asked "is the engine primed with trailing stop?" mid-trade) = he WANTS engine management — but with a deliberate default, not a verdict-dependent accident.
**Evidence:** `setup/scripts/heartbeat_core.py` FIX1 diff (commit `35de43f`); guard `test_audit_fix_heartbeat.py::TestManualCoexistence` tests adoption *occurs*, not which shape.
**Action (before open):** read the adoption code; pin a deliberate default (v15 standard shape: −50% cat-cap + chandelier + 15:50, i.e. manage-not-strangle); add a guard asserting the adopted shape; **emit a Discord ping on adoption** ("adopted your 747P ×5 — managing with v15 shape") so J is never surprised. 30-min fix, after-hours-safe now.

### G2 — Dress-rehearse one tick under the PRODUCTION interpreter.
**What:** all verification tonight ran under `backtest/.venv` python. The scheduled task runs via `run-heartbeat-core.ps1` → pythonw shim. Same env family (per memory: tasks use `backtest/.venv/Scripts/pythonw.exe`) so risk is low — but a WATCH-mode tick end-to-end (both accounts flat → adoption path no-ops, funnel writes, state emits) costs 2 minutes and retires the "import-dead-at-open" scenario entirely.
**Action:** run one dry tick tonight under the exact task command line; confirm `last-tick`/state writes + no stderr.

### G3 — Today's runner exits were never verified or journaled (Rule 8 hole).
**What:** the +$377 was TP1 realizations. The runners (1×747P, 1×750P, ~+$160 unrealized at last look) should have been closed by Gamma_EodFlatten 15:55 — **nobody confirmed the flatten fired, the final fills, or the day's total P&L.** Journal EOD sections still "(pending)".
**Action:** pull account activities/portfolio history for both accounts; confirm flat + final runner P&L; write the journal exits + EOD summary. Also confirms the flatten task itself fired post-changes.

---

## TIER 2 — THE DROPPED J-DIRECTIVES (explicitly demanded tonight, displaced by research excitement)

### G4 — Fleet divergence keystone: promised "next in the chute," never built.
**What:** every fleet arm derives `passed` from **Safe's ENTER** (`build_shared_signal`; `replay_fleet_arms.py:182`) → Safe HOLDs, fleet inert. J demanded 6 independent arms ("maybe one gets in a call, one gets a put early, two ride it with different exits"). Also blocks the ratified one-gate-away doctrine (risky arms take trades Safe skips) AND the R1 forward-farm.
**Trap for the builder:** existing guards PIN the inert design (`test_fleet_producer_keystone.py::test_scoring_peak_off_reverts_fleet_to_inert_BITE`) — changing the keystone means frame-fixing those guards in the SAME commit (L197).
**Action (phased):** Phase 1 = per-arm thresholds/gate-strictness on the same shared perception (cheap, one SEE); Phase 2 = divergent profiles (exit shape, sizing, **a 2DTE forward-test arm on an adequately-funded paper account**, gate looseness). Validate via `replay_fleet_arms.py` before live.

### G5 — The DETECT→ALERT→CAPTURE loop for the discretionary edge: identified twice, never built.
**What:** the architecture that actually made money today (J calls → Gamma executes) has no instrument. Three cheap pieces: (1) **ALERT** — `level_memory.py` (built, look-ahead-safe, finds 750.90) fires a Discord ping on high-memory-level rejection with regime context; the discord-outbox/bridge already exists. (2) **EXECUTE** — J replies "puts 5" and Gamma places (today's manual flow, formalized). (3) **CAPTURE** — every J call becomes a structured anchor row (ts, direction, level, thesis, size, outcome) in a growing `analysis/j-calls/anchors.jsonl`; every future battery's anchor-check reads ALL of them. This is the R3 flywheel — it converts J's screen time into training data instead of losing it.
**Autonomy answer (J objected to "me picking daily"):** autonomy keeps trading everything validated; the alert layer runs IN PARALLEL for the not-yet-mechanizable edge. Not either/or.
**Action:** ~3 small builds, none touching the trading path. Ping-on-detection is log/notify-only → ships without ratification.

### G6 — J's EXACT weekly-options spec was never actually tested.
**What:** tonight tested *neighbors* of J's idea: (a) 2DTE same-day exit (PASS-ish but HOLD on gates), (b) 3-4DTE holds with **premium** stops (−20/−35/−50% → 12% WR gap carnage). J's described trade was different: **OTM weekly put + UNDERLYING-level stop ("put the stop at 750.20") + hold to Friday** — structure-invalidation risk geometry, not premium-% geometry. Never run.
**Evidence:** `multiday-dte34-hold.json` (premium stops only); the 2,958-contract 3-4DTE multi-day cache **now exists** (`backtest/data/options_3dte/,_4dte/`) so this is one cheap pre-registered battery.
**Honest prior:** overnight gaps through the level still hurt; expect modest. But it's HIS spec — test it exactly once, properly, then it's settled either way.

---

## TIER 3 — RESEARCH-INTEGRITY INSTRUMENTS (cheap, compounding)

### G7 — Armability gate in the battery bar.
**What:** chef keeps validating edges the accounts can't afford (ITM2 "best cell — unaffordable"; 2DTE 1.6 lots < 3 floor). No battery checks cost-per-min-lots vs the CURRENT risk budget.
**Action:** add to the canonical battery bar + `promote_keeper`: `min_lot_cost ≤ per-trade risk budget at current equity`, disclosed per cell. One function + doc line in BACKTESTING-PLAYBOOK.

### G8 — Start capturing live greeks/IV NOW (un-proxies all future research, free).
**What:** the dynamic-stop test died partly on "VIX-proxied IV, fixed per-tier delta — no greeks in the cache." But Alpaca's chain endpoint RETURNS full greeks+IV (seen tonight in the 07-10 chain: delta/gamma/theta/vega/IV per contract). The live tick can log the traded contract's greeks at every decision/entry — log-only field, zero trading-path behavior change.
**Action:** extend the decision-row/entry log with a greeks snapshot; a year from now the "does dynamic beat static" question re-opens on REAL data. 30-min build.

### G9 — Sim-to-live parity ledger: entry timing + fill quality.
**What:** every backtest assumes "enter next 5m bar open (+slip)". The live engine ticks each minute on closed bars and posts marketable limits. **The timing/fill gap between validated-sim and live execution has never been measured** — a classic silent alpha-killer. FIX3 (fill reconciliation) now writes `filled_avg_price` → the data exists as of tonight.
**Action:** nightly job diffs each live fill vs the sim-assumed fill for the same signal bar → per-setup slippage + latency distribution → feeds the slippage-breakeven gates with REAL numbers.

### G10 — Recover the truncated audit tail: 6 CONFIRMED findings never delivered.
**What:** the unknown-unknown audit confirmed 11; the synthesis feed truncated after 5. Six confirmed defects are sitting unread in the workflow transcripts.
**Action:** re-run synthesis via `Workflow({scriptPath: ...unknown-unknown-audit..., resumeFromRunId: "wf_a6e5356c-0e7"})` — cached agents return instantly; only synthesis re-runs. Cheap, do early.

---

## TIER 4 — SEE-LAYER & STRUCTURAL

### G11 — Wire `level_memory` as a multi-day level PRODUCER into key-levels.json (A/B first).
**What:** the level feed holds only intraday/recent levels; FIX2 (drop expired) makes it *thinner*. J's verified edge object — the multi-day role-flip shelf (750.90) — **is not in the feed at all**, so the core level-rejection setups (which ARE armed + validated) can't see it. `level_memory.py` is built and anchor-verified; it's a producer waiting for a pipe.
**Trap:** levels feed filter-10 → changing the feed perturbs every validated setup. MUST replay/A-B the feed change through the existing harness before shipping (this is a perception change with entry-path blast radius).

### G12 — Measure whether stale `htf_15m` gates away core winners at the open (from logs, $0).
**What:** the morning diagnosis (htf_15m=BULL through a dump; 50-bar warmup = prior-day data at the open) got dropped when the wick detector died — but htf_15m feeds scoring for the CORE armed setups too. Answerable from `core-decisions.jsonl` history alone: how often does the 09:30–11:00 htf label contradict the realized session trend, and were ENTER verdicts suppressed on those days?
**Action:** one log-analysis script; if the suppression is real and costly, THEN design a fix (don't fix before measuring).

### G13 — Equity doom-loop: Safe-2 down ~32% in 3 weeks; sizing floors are eating the armable set.
**What:** Safe-2 $2,000 (06-15) → $1,352. As equity falls, min-3-lot + risk-caps disqualify more edges (ITM2 gone, 2DTE gone) → only thinner edges remain → worse expectancy → lower equity. Nobody is watching the compounding trajectory; the dual-account experiment's real interim answer is "Safe isn't compounding."
**Action:** treasurer fire (it exists for exactly this): trajectory review + options — (a) paper-reset Safe-2 to $2K **[J decision]**, (b) tier the risk down, (c) accept and document. Also: **does min-3 (2 TP + 1 runner) still bind for single-exit shapes (tp1_qty_fraction=1.0)?** Its provenance is the split structure — per-shape min may legitimately be 1. That's a J rule → flag, don't change.

### G14 — Frame-protection for the futures thesis (contamination risk for the next executor).
**What:** tonight's "multi-day holds lose to gaps" is an **OPTIONS** result (premium positions, 12%-WR lotto geometry). It does NOT transfer to J's directed **futures multiday swing** (no theta, symmetric P&L, stop-geometry — different mechanism entirely). Also note: the futures tick built tonight has a 15:50 time-stop = an INTRADAY engine wired to the *validated intraday* MNQ v3 edge; J's multiday-swing thesis remains a separate, unvalidated, unbuilt thread (overnight-position policy, margin, kill-switch design). Don't conflate the three.

### G15 — Hygiene (batch, low): stale `_j_vwap_cont_doc` says DORMANT while armed; 93 BARE params undrained (`param-provenance.json`); queue.md needs an OP-22 consolidation pass (tonight appended ~10 blocks); SIP cost never quoted to J — web-verify Alpaca Algo Trader Plus pricing (~$99/mo, VERIFY) and hand J the number for the volume-shelf decision.

---

## J-DECISIONS OUTSTANDING (the only three that need him)
1. **Provision futures on Tastytrade `5WW73759`** (broker portal, ~2 min) → MNQ engine goes live-paper.
2. **Safe-2 equity policy** — paper-reset to $2K vs tier down (G13).
3. **Paid SIP data** (~$99/mo, verify) for real volume → unlocks the volume-shelf lens (G15).

## SUGGESTED EXECUTION ORDER FOR OPUS (tonight → tomorrow)
1. G1 adoption-shape pin + ping (before open) → 2. G2 production-interpreter dress tick → 3. G3 runner/journal close-out → 4. G10 recover audit tail → 5. G5 alert+capture loop → 6. G4 fleet phase-1 → 7. G8 greeks capture → 8. G9 parity ledger → 9. G7 armability gate → 10. G6 J-spec weekly battery → 11. G11/G12 SEE-layer (A/B-gated) → 12. G13 treasurer + G15 hygiene.
Everything is paper/reversible except where marked J-decision. Every build ships with a red-proofed guard per tonight's standard.

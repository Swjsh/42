## [2026-07-20 17:00-17:35 ET] NO-SHIP -- Sonnet worker (AFTERHOURS): STRUCTURE-STOP-REFERENCE-LEVEL pre-reg A/B, both candidates REJECT

> **Context.** Assigned STRUCTURE-STOP-ZONE-BAND; on arrival, the queue showed item (a) (buffer
> width) had already been closed REJECT_ALL_CANDIDATES by a conductor session ~5 minutes earlier
> (commit `956cf84`) and item (b) (reference-level choice) had been re-filed standalone as
> `STRUCTURE-STOP-REFERENCE-LEVEL`, status:pending, unclaimed. To avoid duplicating already-
> falsified work (item (a)'s band-width axis) and to avoid clobbering the completed item (a)
> artifacts (the assigned output filename collided with item (a)'s own verdict file), picked up
> the still-open item (b) instead, per its own already-written spec in the queue.

> **Built + ran a frozen pre-reg A/B for item (b)**: `backtest/tools/structure_stop_reference_level_ab.py`
> (new `resolve_zone_boundary`/`reference_level_for` pure functions; reuses
> `structure_stop_study.py`'s trigger recovery/replay machinery + `tw8_level_context.
> frozen_level_set_for_date`'s per-day multi-level active set unchanged). Pre-reg:
> `analysis/recommendations/structure-stop-reference-level-preregistration.json`, frozen BEFORE
> any candidate replay. 3 candidates: REF-EXACT (control, today's live trigger-exact reference),
> REF-ZONE (nearest active level beyond the trigger, away from spot -- the "zone boundary"),
> REF-NONE (no structure stop at all). Band width held at 0.00 for all 3 by rule -- item (a)
> already falsified that axis; re-testing it here without reference-level evidence would be
> fishing. Preflight confirmed the SAME fresh-slice (n=18) + real-fills anchor (n=99,
> 2026-06-29..2026-07-17) populations as item (a), byte-identical hashes -- only the
> trigger_level resolution differs, matching the spec's own stated scope.

> **Result: NO-SHIP both candidates.** REF-ZONE FAILS layer(a) fresh-slice expectancy (-$63.73/tr
> vs -$47.34 control, worse not better). Its layer(b) real-fills "win" (+$481.2 vs -$900.7
> control) is the SAME single-anchor-trade artifact C24 flagged in item (a): ONE 2026-07-08
> position (SPY260708P00741000, 3 legs) drives the entire delta -- the zone boundary (745.21) is
> far enough from the entry-adjacent trigger (744.17) that the structure stop simply never fires
> that day, and the position rides to $427/$427/$307 instead of -$105/+$20/-$81 under today's
> live reference; sub-window split hard sign-flips (+$1473.4 first half vs -$91.5 second half).
> REF-NONE (no structure check at all) fails the same way, worse on layer(a) (-$84.29/tr). This
> directly confirms item (a)'s own finding generalizes: it is not just band-width-on-the-wrong-
> reference that fails to reproduce a stable edge -- the alternative reference itself fails too,
> for the identical single-trade-driven reason.

> **Verified this fire:** new guard `backtest/tests/test_structure_stop_reference_level_ab.py`
> (17/17) covers `resolve_zone_boundary` (7 cases: nearest-above/below, no-level-set, no-trigger,
> no-level-beyond, max-distance, invalid-side), `reference_level_for` (4 cases incl. the
> zone-unavailable fallback), and `build_verdicts`' PASS/FAIL/sign-flip-downgrade/underpowered
> classification (6 cases) + a pinned regression against this fire's actual disclosed NO-SHIP
> output. RED-proofed via file-move (untracked new module -- `git stash` on an unmatched
> pathspec silently no-ops, per tonight's established precedent): moved the module out of
> `backtest/tools/`, confirmed `ModuleNotFoundError` (exact expected mechanism, all 17 fail to
> collect), moved back, re-verified 17/17 green. Broader sweep (`test_structure_stop_study` +
> `test_structure_stop_zone_band_ab` + this file + `automation/state/fleet/test_exit_manager` +
> `test_exit_actuator`) -> **113/113 PASS, 0 regressions**.

> **Rail-4 (PAPER/research-only -- guard test + no revert needed, nothing shipped):** touches
> `backtest/tools/structure_stop_reference_level_ab.py` (new, standalone), `backtest/tests/
> test_structure_stop_reference_level_ab.py` (new guard), `analysis/recommendations/structure-
> stop-reference-level-preregistration.json` + `structure-stop-reference-level-2026-07-20.json`
> (new pre-reg + output), `automation/overnight/queue.md` (item b closed NO-SHIP). **Zero
> trading-path files touched** (`params.json`/`strategies.py`/`exit_manager.py`/placement/exit
> code untouched) -- this is a REJECT research finding exactly like item (a), nothing ships, no
> params flip, no revert needed. `backtest/lib/exit_manager_walk.py` (the faithful tick-managed
> harness) was correctly NOT invoked -- that step is the SHIP-gate verification for a cleared
> candidate, and neither candidate cleared the exploratory pre-reg bar to reach it.

> **Learn-loop:** no new lesson-inbox item -- this is the SECOND time in one evening (item (a),
> then item (b)) that the SAME single 2026-07-08 anchor position drove an apparent layer(b) win
> that a sub-window split then exposed as unstable; this directly re-confirms the already-
> indexed C24 pattern (anchor trades are one-off exceptional setups) rather than surfacing a new
> foot-gun. Both sub-fixes of the original STRUCTURE-STOP-ZONE-BAND queue item are now closed
> NO-SHIP under the same dual-layer discipline -- the queue item itself is fully resolved (no
> further follow-up filed; the 2026-07-20 14:16 exhibit's -$24 vs +$115-130 counterfactual
> remains a single anecdote this evening's research could not generalize into a population-level
> edge).

> **Cost: ~$4** (queue/STATUS read + duplicate-work check, read `exit_manager.py`/
> `tw8_level_context.py`/`structure_stop_study.py`/`structure_stop_zone_band_ab.py` in full to
> design the reference resolver, wrote the pre-reg + ~330-line study tool + guard test, 1 live
> run against real OPRA/fills data (network calls), 1 RED-proof file-move round-trip, 1 broader
> 113-test regression sweep, 2 queue.md edits, this STATUS entry -- no LLM in the hot path, no
> orders, PAPER-only, zero pricing/gate/placement logic touched). **No commit made** (orchestrator
> commits after verification per this fire's own rules).

---

## [2026-07-20 16:42-16:53 ET] SHIP (REVOKE) -- conductor (AFTERHOURS): EXTRA-SIGNAL-CHURN-COOLDOWN item 1 shipped (same-bar re-entry guard), item 2 re-filed as EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT

> **Context.** STAGE 0 engine-health GREEN (13/13, market closed since 15:55). `task_scorer.py
> --top` re-ranked `MORNING-BULL-QUALITY-GATE-RECONSIDER` (J-DECISION-GATED, correctly skipped
> per standing precedent). Grepped live `queue.md` HIGH items: picked `EXTRA-SIGNAL-CHURN-
> COOLDOWN` (filed ~11:25 ET during RTH, explicitly gated "FIX AFTER 16:00" per Rule 9, ready
> now) over `STRUCTURE-STOP-REFERENCE-LEVEL`/`PREMARKET-TOUCH-CREDIT-STUDY` -- a concrete,
> well-scoped mechanism bug with a clear live exhibit, not a fresh multi-day study.

> **Root cause (one sentence):** `_route_extra_setups` (`setup/scripts/heartbeat_core.py`) had
> no memory of "did this setup already attempt an entry on this trigger bar" -- the watchers'
> current-bar guards stop a DUPLICATE signal firing twice, but nothing stopped a FRESH entry
> once the account went flat again mid-bar (a stop-out), so `vix_regime_dayside` fired 3x 748C
> entries within a single closed 5m bar 09:51-09:55 ET (net -$87), only nondeterministically
> slowed by the free-model veto.

> **Fixed:** added a per-arm, per-setup "last trigger-bar attempted" ledger
> (`exit_actuator.load_last_entry_bars`/`record_entry_bar`/`same_bar_cooldown_active`, additive,
> new functions only) wired into `_route_extra_setups`: refuse a new entry for a setup on the
> SAME trigger bar it already attempted one on (`SKIP_COOLDOWN_SAME_BAR`); record only on an
> actual PLACED/PLACING/WOULD_PLACE, never on WATCH_NOT_ARMED/VETOED_BY_MODELS. Chose
> "requires-new-trigger-bar" over a hand-picked N-minute duration -- a brand-new mechanism has
> no trade population to pre-register a numeric cooldown against, so the bar boundary is the
> smallest non-arbitrary unit (no knob to hand-pick). Fail-open throughout; scoped to the
> extra-setup lane only (primary ribbon path untouched, out of this fix's scope).

> **Verified this fire:** new guard `backtest/tests/test_extra_signal_churn_cooldown_2026_07_20.py`
> (10/10) -- round-trip, same-bar-blocks/different-bar-doesn't, fail-open on a cooldown-check
> exception, record-only-on-actual-placement. RED-proofed via `git stash` on the 2 edited files
> (+ file-move for the untracked new test): reproduced the exact expected mechanism
> (`AttributeError: module 'exit_actuator' has no attribute 'load_last_entry_bars'`, 9/10 fail),
> pop restored cleanly, re-verified 10/10 green. Broader sweep (`test_g4_extra_setup_routing` +
> `test_gap_and_go_exit_wiring_2026_07_18` + `test_audit_fix_heartbeat` + `test_audit_fix_exit`
> + `test_execute_stop_display` + `test_g14_fleet_ribbon_exit` + `test_money_path_2026_07_01` +
> `test_trade_to_learn_2026_07_01` + this file) -> **136/136 PASS, 0 regressions**. Curated
> safety gate (31+5-suite) PASS.

> **Rail-4 (PAPER trading-path -- guard test + revert path + this REVOKE report):** touches
> `automation/state/fleet/exit_actuator.py` (additive, 3 new functions), `setup/scripts/
> heartbeat_core.py` (`_route_extra_setups` gains one same-bar check + one recording call;
> zero change to the primary ribbon path/gate ordering/`_execute` pricing logic),
> `backtest/tests/test_extra_signal_churn_cooldown_2026_07_20.py` (new guard),
> `automation/overnight/queue.md` (item 1 closed, item 2 re-filed). **Revert:**
> `git revert fd91712` (1 commit, 4 files touched by the fix + 1 lesson file, additive-only so
> a revert is a clean rollback to today's exact pre-fix churn risk).

> **Item 2 NOT fixed this fire (deliberately):** confirmed live `j_vix_dayside_premium_stop_pct=
> -0.08` / `j_vix_dayside_tp1_pct=0.30` still the stale 2026-06-01-era bracket the item cited,
> unchanged since the 2026-06-18 core-lane chart-stop-primary shift. Did NOT flip it blind --
> C29 (exit knobs validated on one setup/tier don't transfer without independent evidence) --
> re-filed as `EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT` (MED, needs a real pre-reg A/B, small-n
> likely so DEFER-INSUFFICIENT-DATA is an acceptable honest outcome, not a forced flip).

> **Learn-loop:** filed `strategy/candidates/_lesson-inbox/extra-signal-same-bar-churn-2026-07-20.md`
> -- flags that the PRIMARY ribbon path has no equivalent same-bar re-entry guard (currently
> protected only by its own flat-check + gate discipline, a materially different and untested-
> for-this-exact-shape safety net) as the first place to look if this churn class ever
> reappears there.

> **Cost: ~$5.0** (STAGE 0/1 reads, `task_scorer.py --top`, queue.md HIGH-item grep + read,
> traced `setup_dispatch.py`/`heartbeat_core.py`'s extra-setup dispatch+route+exec path in full,
> `exit_actuator.py`/`exit_manager.py` exit-action stage/reason vocabulary, confirmed
> `params.json`'s live `j_vix_dayside_*` values, designed+wrote the same-bar cooldown mechanism
> (3 new exit_actuator functions + heartbeat_core wiring), wrote+ran the 10-test guard file
> (2 full syntax checks, 1 targeted run, 1 broader 136-test sweep), 1 RED-proof git-stash +
> file-move round-trip, 1 curated safety-gate run, 2 queue.md edits (closure + new item), 1
> lesson-inbox file, 1 commit, 1 verify-committed check, this STATUS entry -- no LLM in the hot
> path, no orders, PAPER-only, zero pricing/gate/placement logic touched). **Files:**
> `automation/state/fleet/exit_actuator.py`, `setup/scripts/heartbeat_core.py`,
> `backtest/tests/test_extra_signal_churn_cooldown_2026_07_20.py`, `automation/overnight/queue.md`,
> `strategy/candidates/_lesson-inbox/extra-signal-same-bar-churn-2026-07-20.md`. **Commit:**
> `fd91712`.

---

## [2026-07-20 16:19-17:xx ET] OK -- conductor (AFTERHOURS): STRUCTURE-STOP-ZONE-BAND item (a) closed REJECT_ALL_CANDIDATES; item (b) re-filed as STRUCTURE-STOP-REFERENCE-LEVEL

> **Context.** STAGE 0 GREEN (engine-health 13/13, market closed since 15:55). Top HIGH item:
> J's live-called exit today 14:01-14:26 ET -- safe 3x 745P structure-stopped on a 12-cent
> overshoot of the exact trigger level while the ribbon stayed BEAR and price never decisively
> broke the surrounding key-level zone (-$24 actual vs a ~+$115-130 counterfactual). Filed as
> `STRUCTURE-STOP-ZONE-BAND` with two sub-fixes: (a) proximity band on the close-above test,
> (b) reference-level choice (trigger-exact vs zone boundary).

> **Built + ran a frozen pre-reg A/B for item (a) only** (reference-level choice needs new
> wiring, scoped out -- see below): `backtest/tools/structure_stop_zone_band_ab.py`, reusing
> `structure_stop_study.py`'s already-validated trigger-recovery/replay machinery unchanged,
> held the LIVE SS-B exit shape fixed, swept ONLY the buffer width (0.00 control / 0.05/0.08/
> 0.10/0.12/0.15/0.20) against real-fills anchor (99 positions, 2026-06-29..2026-07-17, hash-
> pinned) + an independent 18-signal fresh-slice population, plus a sub-window (first-half vs
> second-half) stability check the 2026-07-09 predecessor study didn't have.

> **Result: REJECT_ALL_CANDIDATES.** Every non-zero buffer FAILS the fresh-slice layer (worse
> expectancy than the 0-buffer control, every single candidate). The real-fills anchor "wins"
> for BAND-10/12/15/20 (+$677 to +$801 vs -$900.7 control) are a single-trade artifact: ONE
> 2026-07-08 signal (SPY260708P00741000, 4 arms, $532/388/331 per-leg swings) accounts for the
> entire delta, and the sub-window split hard SIGN-FLIPS (+$1656-1736 first half vs -$34.5 to
> -$74.5 second half) -- the exact single-anchor-trade-driving-everything signature C24 warns
> against. This is an honest negative result that directly CONFIRMS the original queue item's
> own quantified counterfactual table: widening the band on the SAME (trigger-exact) reference
> doesn't reproduce a stable edge -- the REFERENCE CHOICE is the real lever, not band width.
> BAND-00 (today's actual live behavior) stays unchanged; nothing shipped to the trading path.

> **Verified this fire:** new guard `backtest/tests/test_structure_stop_zone_band_ab.py` (7/7)
> covers the one novel piece of logic (`build_verdicts`'s dual-layer gate + sub-window sign-flip
> + underpowered-n<15 downgrade), including a pinned regression test against this fire's actual
> disclosed REJECT_ALL output. **RED-proofed via file-move** (the module is untracked -- `git
> stash` on an untracked-file pathspec silently no-ops rather than stashing it, see the
> blast-radius note below): moved `structure_stop_zone_band_ab.py` out of `backtest/tools/`,
> confirmed `ModuleNotFoundError` (exact expected mechanism), moved back, re-verified 7/7 green.
> Curated safety gate (31 + 5-suite) PASS.

> **Blast-radius near-miss, no lesson needed (self-corrected within the fire):** attempted
> `git stash -- backtest/tools/structure_stop_zone_band_ab.py` (untracked file -- pathspec
> stashing needs `-u`/`git add` first) to RED-proof; the command errored/aborted and stashed
> NOTHING. `git stash list` then surfaced TWO pre-existing stashes unrelated to this fire
> (base commits 2026-07-18, from an earlier session) -- confirmed via `git rev-parse
> stash@{0}^1` that neither predates nor was touched by anything this fire did. No recovery
> action needed; left both pre-existing stashes untouched (not this fire's mess to clean up,
> flagging only for visibility) and switched to the file-move RED-proof technique used for the
> rest of this fire.

> **Rail-4 (PAPER/research-only -- guard test + revert path + this REVOKE report):** touches
> `backtest/tools/structure_stop_zone_band_ab.py` (new, standalone), `backtest/tests/
> test_structure_stop_zone_band_ab.py` (new guard), `analysis/recommendations/structure-stop-
> zone-band-preregistration.json` + `structure-stop-zone-band-2026-07-20.json` (new pre-reg +
> output), `automation/overnight/queue.md` (item a closed, item b re-filed as
> `STRUCTURE-STOP-REFERENCE-LEVEL`). **Zero trading-path files touched** (`params.json`/
> `strategies.py`/`exit_manager.py`/placement/exit code untouched) -- this is a REJECT research
> finding, nothing ships, no params flip, no revert needed. **Revert:** `git revert <commit>`
> if ever needed (1 commit, 5 files).

> **Learn-loop:** no new lesson-inbox item -- the sub-window-sign-flip / single-trade-driving-
> everything finding directly confirms the already-indexed C24 pattern (anchor trades are one-
> off exceptional setups) rather than surfacing a new foot-gun. One methodology note worth
> keeping inline (not a new L##): when RED-proofing an UNTRACKED new module, `git stash` on a
> pathspec that doesn't match silently no-ops rather than erroring loudly enough to notice at a
> glance -- the file-move technique (used successfully in the 2026-07-20 SAFE-VIX-CONDITIONAL-
> SIZING fire) is the safer default for any future untracked-file RED-proof in this repo.

> **Cost: ~$4.1** (STAGE 0/1 reads, queue.md HIGH-item scan, traced `exit_manager.py`'s
> `nearest_active_level`/`_structure_stop_hit`/`ExitState.from_entry` + `heartbeat_core.py`'s
> trigger_level resolution (~150 lines), read `structure_stop_study.py` in full (~700 lines,
> reused machinery) + its 2026-07-09 output JSON verdicts, checked SPY 5m cache coverage
> (extended discovery to 2026-07-20, adjusted LEVEL_HISTORY_START), computed + froze a new
> anchor-population hash (99 positions), wrote the pre-registration JSON, wrote the ~360-line
> study script, ran it live (2 Alpaca OPRA network fetch passes, layer a + layer b), diagnosed
> the single-trade-driving-everything result via a targeted row-diff script, wrote + ran the
> new 7-test guard file, RED-proofed via file-move, ran curated safety gate, investigated +
> recovered from a git-stash near-miss, 2 queue.md edits (closed item a, filed item b), 1
> STATUS.md entry, 1 commit -- no LLM in the hot path, no orders, PAPER-only research, zero
> trading-path files touched). **Files:** `backtest/tools/structure_stop_zone_band_ab.py`,
> `backtest/tests/test_structure_stop_zone_band_ab.py`, `analysis/recommendations/structure-
> stop-zone-band-preregistration.json`, `analysis/recommendations/structure-stop-zone-band-
> 2026-07-20.json`, `automation/overnight/queue.md`. **Commit:** `956cf84`.

---

## [2026-07-20 16:12-16:35 ET] OK -- conductor (AFTERHOURS): fixed a false ENTER-AFTER-CEILING alarm in fill_funnel.py -- REVOKE-eligible, guard-tested, committed

> **Context (`et_clock.py` 16:12 ET Monday, market closed since 15:55).** STAGE 0: engine-health GREEN (13/13). STATUS showed six `DEGRADED: FILL-FUNNEL ENTER AFTER CEILING[core:bold/safe]` flags from the 16:09:57 self-check for entries at 15:41-15:45 ET. Investigated per priority-1 (FUNCTION FIRST): pulled the raw `core-decisions.jsonl` rows -- every flagged row had `verdict:"ENTER_BEAR"` but `action:"SKIP_LATE_ENTRY"` and **no `exec` dict at all** (heartbeat_core.py's `_past_entry_ceiling` gate correctly fired, zero broker attempts -- `fill_funnel`'s own `attempted` count was already 0 for these). **Root cause (one sentence):** `fill_funnel.py`'s ceiling-bypass check keyed off the pre-gate `verdict` field instead of the post-gate `action` field, so a row the ceiling gate *already caught* was double-counted as a ceiling *bypass* -- a producer/consumer field mismatch between heartbeat_core's own two truth fields.
>
> **Fix:** `setup/scripts/fill_funnel.py` -- only append to `enters_after_ceiling` when the row was NOT already gated (`action != SKIP_LATE_ENTRY` core / `placement.reason != SKIP_LATE_ENTRY` fleet). Verified against real 2026-07-20 data: funnel flips DEGRADED->**GREEN**, `automation/state/fill-funnel-2026-07-20.json` rewritten. Regression-pinned: the 2026-07-01 pre-ceiling-gate fixture (a genuine bypass, `action:"PLACE_FAIL"`, real broker attempt) still correctly flags -- confirms this narrows the false positive without swallowing a real fault. 4 new tests + 18 pre-existing all green: `backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_fill_funnel_guard.py -q` -> `22 passed`.
>
> **Rail-4 (PAPER trading-path carve-out):** read-only diagnostics file, never touches placement/order code. Guard test + git-revert (`git revert 270e9ca`) both in place -- REVOKE, not pre-approve. Committed `270e9ca`, pre-commit safety gate PASS (curated 5-suite). No J ping needed (diagnostics-only, doesn't touch live doctrine/params).
>
> **Why this matters beyond today:** this exact false alarm would have fired again every trading day the engine correctly declines a late-session ENTER (routine, by design) -- eroding trust in the funnel's real RED/DEGRADED signal (OP-33 visibility discipline: a noisy instrument gets ignored right when a genuine bypass needs to cut through).

---

## [2026-07-20 ~09:30-09:36 ET] GREEN -- interactive (Fable): Monday pre-open verify complete, all 4 debut/live tasks FIRING with real output quoted

> **Context (`et_clock.py`: `2026-07-20 09:30:34 Monday EDT market_hours=True`).** Final check of the morning preflight (breakers re-armed 08:02 after the STATE-FILE-REVERSION incident; Bold margin_pdt flip cc1a2bd; bias fresh `2026-07-20 bearish`; both accounts flat, zero stray orders -- all verified 09:06). Check 4 (the 09:25-09:30 debut fires), verified with REAL OUTPUT per OP-33, not wrapper exit codes:
> - **Gamma_HeartbeatCore** fired 09:30:01, exit 0 -- PROOF: two fresh `core-decisions.jsonl` rows at 09:34 (safe `SKIP_STRUCTURE_VETO` + bold `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`, both `armed:true`, context_bundle v2 attached, and the stale Friday-15:55 trendline trigger correctly caught by `SKIP_STALE_TRIGGER`).
> - **Gamma_JIntentExecutor** (debut) fired 09:25, exit 0 -- `j-intents.json` intents=[] => pure no-op loop, as designed.
> - **Gamma_ConductorRTH** (debut) fired 09:30, exit 0 -- prior 09:12 AFTERHOURS fire logged to `conductor-outcomes.jsonl`; RTH_LIGHT pass running on 30-min cadence.
> - **Gamma_FuturesEdge3Sim** (debut) fired 09:30, exit 0 -- PROOF: `automation/state/logs/futures-edge3-sim-2026-07-20.log` `[09:30:02] pass complete {"action":"tick","in_rth":true,...}` + 09:35 tick; state files under `automation/state/futures/` updating.
>
> Engine owns the session from here. No interactive scheduling remains. New queue item filed this pass: PREMARKET-TOUCH-CREDIT-STUDY (J's 747.46 premarket-rejection question -- engine gives zero touch-credit to premarket rejections).

---

## [2026-07-20 ~09:12-09:16 ET] OK (light) -- conductor (AFTERHOURS, market opens 09:30 -- deliberately kept small): engine GREEN, no safe bounded build started this close to open

> **Context (`et_clock.py`: `2026-07-20 09:14 Monday EDT market_hours=False`, Task=conductor).** Woke ~18 min before market open. STAGE 0 engine-health GREEN (13/13 checks). `task_scorer.py --top` again ranked `MORNING-BULL-QUALITY-GATE-RECONSIDER` (J-DECISION-GATED, Nth recurrence, correctly skipped). Self-audit gaps confirmed fully actioned through the 07-19 21:xx consensus-leadin fix -- no new batches. Grepped `queue.md` HIGH items live: every one that's genuinely one-fire-bounded was already drained by tonight's 4 prior fires (00:19/02:19/04:19/06:19/08:19); the remaining HIGH items (`ENGINE-VECTORIZATION`, `GATE-TIERS-IMPLEMENT`, `D1-TV-CDP-ROOT-CAUSE`, `SINGLE-STRATEGY-REGISTRY-DESIGN` remainder, `MM-05-WAKE-FIRE-REVIVAL`, `DIRECTION-BLOCK-BATCH-RECONCILE`) are all multi-step builds or J-gated, not startable with ~15 min of runway before rail-1's hard RTH boundary.

> **Deliberate judgment call:** rather than start a build that could bleed into 09:30 ET (exactly the L54 failure shape -- a conductor fan-out starving the live heartbeat), used the remaining time to re-verify `TASK-SCORER-STATUS-VOCAB-GAP` (LOW hygiene item): live-grepped every `status:todo` line in `queue.md` -- only 2 exist, F3 (already `status:done`) and `PDT-WIRE-FLEET-ARMS` (genuinely blocked by its own open `depends:`), so **zero currently-open items are actually hidden by the scorer's vocab gap right now**. Annotated the item in-place rather than rushing the broader fix (which needs a real per-status audit across `todo`/`queued`(18)/`proposed`(12)/`open`(2) -- many `proposed` items are deliberately spec-only and would become false-ready if the regex were widened carelessly).

> **Rail-1 discipline:** zero code/trading-path files touched. Only `automation/overnight/queue.md` (1 annotation) + this STATUS entry. No Agent-tool fan-out this fire -- correctly small given the clock. Next AFTERHOURS-mode fire is this evening (18:00+ ET); `Gamma_ConductorRTH` covers the light verify-and-flag pass through the trading day.

> **Cost: ~$1.7** (STAGE 0/1 reads, `task_scorer.py --top`, self-audit gaps re-confirmation, HIGH-item live re-grep + readiness triage, `status:todo` re-audit for TASK-SCORER-STATUS-VOCAB-GAP, 1 queue.md annotation, 1 commit -- no LLM in hot path, no orders, zero trading-path files touched). **Files:** `automation/overnight/queue.md`.

---

## [2026-07-20 ~08:19-08:35 ET] SHIP (REVOKE) -- conductor (AFTERHOURS): 2 stale HIGH queue items closed (GATE-ORDERING-FIX-RELAUNCH, TV-MCP-DRAW-API-FIX-REOPENED) -- both already fixed, checkboxes never flipped

> **Context (`et_clock.py`: `2026-07-20 08:19 Monday EDT market_hours=False`, Task=conductor).** STAGE 0 engine-health GREEN (13/13 checks, market closed/quiet). `task_scorer.py --top` again ranked `MORNING-BULL-QUALITY-GATE-RECONSIDER` — re-confirmed J-DECISION-GATED (Nth recurrence). Self-audit gaps (`analysis/self-audit/new-gaps-flagged.md`) fully actioned, no new batches since 07-19 21:xx. Grepped `queue.md` for open `(HIGH` items (14 hits) and picked 2 candidates worth tracing before building: `GATE-ORDERING-FIX-RELAUNCH` ("confirmed-bug", trading-path) and `TV-MCP-DRAW-API-FIX-REOPENED` ("confirmed FABRICATED by a judge").

> **Both turned out to be stale — already fixed, never closed.** (1) `GATE-ORDERING-FIX-RELAUNCH` claimed a "dead crew died on session limit BEFORE editing." Live-read `heartbeat_core.py::run_account` lines 911-946: the exact fix (stale-trigger-bar check moved unconditionally to the TOP of the post-verdict ladder, before any ENTER/SKIP branch) is present verbatim, with an inline dated comment citing the SAME `GATE-PROVENANCE-SWEEP-2026-07-10.md` doc the item points to. Guard `test_gate_provenance_ordering_2026_07_10.py` exists on main — re-ran live: **17/17 PASS**. (2) `TV-MCP-DRAW-API-FIX-REOPENED` claimed a judge "verified: commit nonexistent, test file nonexistent, bug still live" in the tradingview-mcp server's `drawing.js`. Read the live file at `SwjshAlgoKnife\mcp-servers\tradingview-mcp\src\core\drawing.js`: `listDrawings`/`getProperties`/`removeOne`/`clearAll` all correctly call `_resolve(_deps)`. `git log` on that repo shows the real fix landed 2026-07-14 10:12 MT (commit `6f25ce4`, author "Sauce Bot", root-cause message matches exactly), with a real test file `tests/drawing_getchartapi.test.js` — re-ran live: **5/5 PASS**. No dist/build step in that package, so no staleness risk between `src/` and what the MCP server actually imports; the fix is genuinely live on the path every Claude Code session's stdio-spawned server uses.

> **Verified this fire:** both guard suites re-run fresh (17/17 + 5/5, both green, quoted above) — not assumed from the queue item's own text. No source code changed in either the `42` repo or (READ-ONLY) `SwjshAlgoKnife` — this was pure verification + queue-hygiene closure, the same class as the 2026-07-11 "stale checkbox, shipped work" closures for G11/CROSS-TICKER/CRYPTO-TWIN-T1-T4.

> **Rail-4 N/A (no trading-path/code change):** only `automation/overnight/queue.md` touched (2 items flipped `[ ]`→`[x]` with evidence). Zero `params.json`/`heartbeat_core.py`/`filters.py`/placement/exit files edited. **Revert:** `git revert <this commit>` (1 file).

> **Learn-loop:** no new lesson-inbox item filed — this is a second/third instance of an already-indexed pattern (a queue item's premise going stale once the described work is actually completed by a *different* fire/session that never closed the loop, e.g. the 2026-07-20 04:19 fire's "false-premise citation" and the 2026-07-11 hygiene pass). Worth a standing note for future fires: **before building a HIGH item, grep the target file/test for the fix's own described symptom FIRST** — cheap ($0 code reads) and caught 2 already-done builds this fire before any code was written, which would otherwise have wasted a full build-cycle re-deriving work that already shipped.

> **Cost: ~$2.3** (STAGE 0/1: engine-health/STATUS/queue reads, `task_scorer.py --top` re-trace, self-audit gaps confirmation, grep for open HIGH items, live trace of 2 candidate items across `heartbeat_core.py`, the referenced audit doc, `drawing.js`, and the tradingview-mcp repo's git log/test suite, 2 live test-suite runs (17/17 + 5/5), 2 queue.md closures, 1 commit — no LLM in the hot path, no orders, no code edits outside queue.md). **Files:** `automation/overnight/queue.md`.

---

## [2026-07-20 ~06:19-06:44 ET] SHIP (REVOKE) -- conductor (AFTERHOURS): PROFIT-P4-NBBO-CAPTURE closed -- entry-side option NBBO threaded into decision rows

> **Context (`et_clock.py`: `2026-07-20 06:19 Monday EDT market_hours=False`, Task=conductor).** STAGE 0 engine-health GREEN (13/13 checks GREEN, market closed/quiet). `task_scorer.py --top` again ranked `MORNING-BULL-QUALITY-GATE-RECONSIDER` -- re-confirmed J-DECISION-GATED, not fabricatable in one bounded fire (Nth recurrence). Self-audit gaps surface (`analysis/self-audit/new-gaps-flagged.md`, 14 batches) checked: the noise-filter fix from the 07-19 21:48 fire holds; the remaining un-actioned SUBSTANTIVE items across the 07-02/07-08/07-09/07-10/07-11/07-13 batches are broad multi-week-scale audit asks ("automated backup and state recovery", "real-time model drift detection", etc.), not one-fire bounded -- noted, not actioned, correctly deferred rather than force-fit. Grepped `queue.md` for open `(HIGH` items directly (scorer's own scope gap, noted by the prior fire, still not fixed) and picked `PROFIT-P4-NBBO-CAPTURE`: a small, precisely-scoped, additive-telemetry ask ("Persist option NBBO ... Additive telemetry on heartbeat_core decision logging + guard test") -- the same class as the last 3 fires' successful `trigger_level_exact`/`shadow_triggers_fired`/same-day-tier threading work.

> **Traced before building:** the item's own "entry/exit event" framing turned out to be half-already-true. `exit_actuator.manage_tick`'s per-tick results already carry `best_premium`/`worst_premium` (literally ask/bid from `get_option_quote_hilo`, added 2026-07-09 for STRUCTURE-STOP visibility) and that list threads verbatim into `rec["exit_pass"]` in `heartbeat_core.run_account` -- so exit-side NBBO was already reaching `core-decisions.jsonl`, just under different field names. The genuine, un-closed gap was ENTRY-side: `_execute`'s `plan` dict (persisted as `rec["exec"]`) computed `mid` (`get_option_mid`) and `entry_px` (`marketable_limit_price`) every tick but discarded the bid/ask that produced them.

> **Fixed (1 source file, additive-only):** `_execute` now reconstructs `plan["nbbo"] = {bid, ask, mid, spread}` from the SAME `mid`/`entry_px` already computed this tick -- `ask = entry_px - buffer` and `bid = 2*mid - ask` (both formulas are the existing `marketable_limit_price`/`get_option_mid` arithmetic, algebraically inverted). Deliberately NOT a third independent `get_option_quote_hilo` fetch: existing tests mock only `get_option_mid`+`marketable_limit_price` on this path (mirroring the established `test_audit_fix_heartbeat.py` pattern), and a genuine extra fetch would add a real network round-trip to the entry-critical path plus risk a race between 3 separate quote reads on the same symbol. Zero change to `mid`/`entry_px`/`tp`/`stop`/`qty`/gate logic -- pure additive key on the `plan` dict.

> **Verified this fire:** new guard `backtest/tests/test_nbbo_capture_2026_07_20.py` (5/5) -- dry-plan exact-value reconstruction pin (mid=1.00/entry_px=1.08/buffer=0.03 -> bid=0.95/ask=1.05/spread=0.10), a non-default `entry_cross_buffer` inversion check, an explicit "must never call `get_option_quote_hilo`" pin (fails the test outright if a future edit adds a real 3rd fetch), an end-to-end dry=False PLACED-row persistence + JSON-serializability check, and a NO_PREMIUM short-circuit check (nbbo key absent, never a None-valued fake telemetry entry). **RED-proofed via `git stash`** on the single edited file: 4/5 new tests failed with the exact expected mechanism (`KeyError: 'nbbo'`); `git stash pop` restored cleanly (`git diff --stat` confirmed the intended 2-hunk, ~18-line diff), re-verified 5/5 green. Broader sweep (`test_audit_fix_heartbeat.py`+`test_money_path_2026_07_01.py`+`test_trade_to_learn_2026_07_01.py`+`test_min_entry_premium_floor.py`+`test_real_fill_guard.py`+this file) -> **100/100 PASS, 0 regressions**. Curated safety gate (31+5-suite) PASS, run via the commit hook.

> **Rail-4 (PAPER/entry-telemetry-only -- guard test + revert path + this REVOKE report):** touches `setup/scripts/heartbeat_core.py` (`_execute`'s `plan` dict gains one additive key only -- no pricing/sizing/gate/placement logic changed), `backtest/tests/test_nbbo_capture_2026_07_20.py` (new guard), `automation/overnight/queue.md` (item closed with the exit-side-already-present correction documented inline). Zero change to any order-placement/sizing/exit behavior -- this is pure LOGGED-ONLY entry telemetry, the same class as the 2026-07-09 `trigger_level_exact` and 2026-07-19 `shadow_triggers_fired` precedents. **Revert:** `git revert 50fa30f` (single pathspec commit, 3 files).

> **Learn-loop:** no new lesson-inbox item filed -- this is a direct, uneventful application of the already-proven "LOGGED-ONLY additive telemetry, reuse the tick's existing broker calls instead of adding a new fetch" pattern to a third field family (after `trigger_level_exact` and `shadow_triggers_fired`); no new foot-gun surfaced. One thing worth flagging inline (not a new L##, just a scope note): `fleet_live.py` (lines 322/326) and `j_intent_executor.py` (line 483) have the IDENTICAL `get_option_mid`+`marketable_limit_price` double-call shape on their own separate entry paths (fleet-arm live trading + J-called manual entries) and are candidates for the same NBBO-reconstruction treatment in a future slice -- left untouched this fire since the queue item's own scope named "heartbeat_core decision logging" specifically.

> **Cost: ~$3.9** (STAGE 0/1: engine-health/STATUS/queue reads, `task_scorer.py --top` re-trace (correctly re-rejected), self-audit gaps full-batch review across 14 dated sections (correctly deferred the remaining broad multi-week asks as not one-fire-bounded), grep for open HIGH items + targeted section reads, existing-quote-fetch-pattern discovery across `fleet_broker.py`/`heartbeat_core.py`/`exit_actuator.py`/`fleet_live.py`/`j_intent_executor.py` (confirmed the exit-side gap was already closed before building anything), 1 source-file edit (2 hunks, ~18 lines), 1 new 5-test guard file, 1 targeted pytest run (5/5), 1 RED-proof git-stash round-trip, 1 broader 100-test regression sweep, 1 curated safety-gate run (commit hook), 1 queue.md closure edit, 1 commit -- no LLM in the hot path, no orders, PAPER-only, zero pricing/gate/placement logic touched). **Files:** `setup/scripts/heartbeat_core.py`, `backtest/tests/test_nbbo_capture_2026_07_20.py`, `automation/overnight/queue.md`. **Commit:** `50fa30f`.

---

## [2026-07-20 ~04:19-04:41 ET] SHIP (REVOKE) -- conductor (AFTERHOURS): TRENDLINE-FIXES-2026-07-17 item 2 closed -- same-day priority tier

> **Context (`et_clock.py`: `2026-07-20 04:19 Monday EDT market_hours=False`, Task=conductor).** STAGE 0 engine-health GREEN (13/13 checks GREEN, market closed/quiet). `task_scorer.py --top` again ranked `MORNING-BULL-QUALITY-GATE-RECONSIDER` — re-confirmed J-DECISION-GATED, not fabricatable in one bounded fire (Nth recurrence). Self-audit gaps surface (`analysis/self-audit/new-gaps-flagged.md`) confirmed fully actioned — the 07-19 21:48 noise-filter fix's own DONE marker states future re-extracts will correctly reject the remaining 07-18-batch lines as scaffold, verified this fire by re-reading the batch (no un-actioned real gaps left). `task_scorer.py`'s Active-backlog ranking never surfaces HIGH items (confirmed: 0/34 scored items are HIGH — a scope gap in the scorer itself, since HIGH items live in dated sub-sections below `## Active backlog`, not parsed; noted for a future fire, not fixed this one) so grepped `queue.md` directly for open `(HIGH` items (15 found). Picked `TRENDLINE-FIXES-2026-07-17` item 2 (item 1 closed 00:xx, item 4 closed 22:xx last night; items 2/3 were flagged by both prior fires as "needs its own eval/design work" — traced item 2 far enough to confirm it WAS actually one-fire-bounded once its false premise was corrected).

> **Traced before building:** item 2 claimed a "pre-reg A/B spec already in TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14" for the same-day-priority-tier gap. Read the referenced pre-reg (`analysis/recommendations/trendline-structure-conviction-preregistration.json`) in full: it answers a COMPLETELY DIFFERENT question (a VIX-band conviction override for `block_elite_bull`, motivated by a 2026-07-14 11:06 ET exhibit signal) and is already `status: RUN_COMPLETE` / `result_verdict: KILL` (dated 2026-07-14). The audit doc's own "Not done / explicitly deferred" section states the same-day-priority tier "needs its own eval, not bundled into this audit's read-mostly fixes" — i.e. no A/B spec was ever written for THIS gap; the queue item's premise was simply wrong. Corrected this explicitly in `queue.md` rather than silently building on the false citation.

> **Re-scoped the validation method to match what the feature actually is:** `write_live_state`'s own docstring states "the engine does NOT trade off these yet" — this is a SHADOW-only visibility feature (surfaces J's same-day line on the chart/JSON, never an input to any trading gate), not a live decision. No P&L A/B applies; the correct validation is a mechanism-correctness guard, the same class as item 1 (draw-skip visibility) and item 4 (shadow_triggers_fired threading), both already shipped this way in the last 2 fires.

> **Traced the root gap:** `trendline_engine._fit`'s own score (`respect - 5*violations + span*0.1`) structurally rewards longer-lived lines — a fresh 2-3-touch same-day line J hand-draws essentially never wins a (kind, family) slot over an older multi-day line sharing it, because `detect()` only ever returns ONE best-scoring line per (kind, family) across the WHOLE lookback window. Confirmed via a synthetic fixture (2 disjoint-price-range trading days, hand-placed pivots, iteratively verified live via a scratch script before committing to the test — the first 2 fixture attempts accidentally created unintended cross-day/rising-trend pivot structure and were discarded, not silently kept).

> **Fixed (2 files, additive-only):** `trendline_engine.py` — `Trendline` gained `tier: str = "primary"` (default preserves every existing reader/caller byte-identical); `detect(bars, families=..., include_same_day_tier: bool = False)` (new kwarg, default False = zero behavior change for the 6+ existing call sites across `v52_trendline_break.py`/`trendline_conviction_override_study.py`/tests, all of which call with defaults) adds a second best-scoring pass restricted to bars matching the LAST bar's ET calendar date, appending a result tagged `tier="same_day"` only when it is a genuinely different line from its primary sibling (deduped on exact anchor identity `a_et`/`b_et`, never a duplicate). No-look-ahead is inherited for free — the same-day slice only ever narrows the ALREADY-truncated `bars` the caller passed in, never reads beyond it (C6 invariant, proven by a dedicated no-lookahead guard). Wired live at `main()` (`include_same_day_tier=True`) — the ONE production entry point both `Gamma_Trendlines` (5-min RTH cadence) and the premarket drawing bridge (`--json` mode) call; `write_live_state`'s JSON payload now carries `tier` per line.

> **Deliberately did NOT wire same-day lines into the drawing skill's on-chart selection.** `.claude/skills/trendline-draw/SKILL.md`'s existing DRAW CAP (added 2026-07-15 after J's "way too many trend lines on the screen" complaint) already caps the chart to 1 line per side by `respect_count` — adding same-day lines to that pool would reopen exactly that noise complaint, and is item 3's explicit scope (zoom-aware drawing), not item 2's. Updated the SKILL.md doc to state this explicitly (same-day lines now exist in the JSON/log/shadow-state for self_check/dashboard/future consumers, excluded from the draw-cap selection pending item 3) so a future fire tackling item 3 knows to reconsider the two together, rather than silently dropping the connection.

> **Verified this fire:** new guard `backtest/tests/test_trendline_same_day_tier.py` (9/9) — default-unchanged (no kwarg == explicit False), additive-never-replaces-primary, dedup-when-primary-already-is-same-day (single-day fixture), no-op-when-no-distinct-today-line, no-lookahead (mirrors `test_trendline_conviction_override_no_lookahead.py`'s truncation-invariance pattern), `write_live_state` schema carries `tier`, and `families=("wick","body")` (the production default) doesn't crash with the new kwarg. **RED-proofed via `git stash`** on the 2 edited source files (kept the new test file in place): all 9 tests failed with the exact expected mechanism (`TypeError: detect() got an unexpected keyword argument 'include_same_day_tier'`); `git stash pop` restored cleanly (`git diff --stat` confirmed the intended 2-file, 72-insertion/16-deletion diff), re-verified 24/24 green (new file + `test_trendline_engine.py` + `test_trendline_multiday.py` + `test_trendline_live_state.py`). Broader sweep (`-k trendline`, whole repo, matches the exact command the 2026-07-14 audit used) → **86/86 PASS, 0 regressions** (403.85s — the same ~6-7 min this sweep has always taken per the audit's own recorded 364.63s baseline, not a new slowdown). Curated safety gate (31 + 5-suite) PASS, run twice (before and after the stash round-trip).

> **Rail-4 (PAPER/visibility-only — guard test + revert path + this REVOKE report):** touches `backtest/autoresearch/trendline_engine.py` (new `tier` field + `include_same_day_tier` kwarg, default-False/additive-only), `.claude/skills/trendline-draw/SKILL.md` (doc text — same_day lines exist in JSON, excluded from draw selection), `backtest/tests/test_trendline_same_day_tier.py` (new guard), `automation/overnight/queue.md` (item 2 of TRENDLINE-FIXES-2026-07-17 closed + false-premise correction; also closed the stale `T-GYM-20260717` HIGH item — live-checked `crypto/data/scorecards/latest.json`, `104/104 pass` as of this fire, a later scheduled gym run self-resolved the 1 prior failure). **Zero trading-path files** (`params.json`/`heartbeat_core.py`/`filters.py`/placement/exit code untouched) — `trendline_engine.py` is a SHADOW-only structure-visibility producer, never fed to entries (entry-wire is separately A/B-gated NEEDS-REVIEW per its own docstring, untouched here). **Revert:** `git revert <this commit>` (single pathspec commit, 4 files: `trendline_engine.py`, `SKILL.md`, the new test, `queue.md`).

> **Learn-loop:** no new lesson-inbox item filed — this is a direct instance of an already-indexed pattern (a queue item's premise citing a real artifact that, on inspection, answers a different question than claimed) rather than a new foot-gun; the correction is recorded inline in `queue.md` itself so the next reader doesn't re-trust the stale citation. One methodology note worth keeping: when a fixture-construction script's first 1-2 attempts produce unintended structure (accidental cross-day pivots, unintended local trends from a "rising baseline"), iterate live via a scratch script BEFORE writing the committed test — this fire hit exactly that twice (documented in the exploration, not in the shipped test) and the third, disjoint-price-range design worked cleanly on the first try.

> **Cost: ~$3.85** (STAGE 0/1: engine-health/STATUS/queue reads, self-audit gaps re-confirmation, `task_scorer.py --top` + full-ranking read (confirmed 0 HIGH items scored — scope gap noted, not fixed), grep for open `(HIGH` items across the whole queue.md (15 found, read in full), read of `TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14.md`'s relevant sections + the referenced pre-reg JSON in full (caught the false-premise mismatch), read of `trendline_engine.py`'s detect/_fit/find_pivots (~200 lines) + grep for all callers/consumers across the repo (6+ call sites, all default-arg), read of `trendline_draw_state.py` + `SKILL.md` for drawing-bridge assumptions, 3 iterative scratch-script fixture explorations (2 discarded for unintended structure) before landing the clean 2-disjoint-day design, 2 source-file edits (dataclass field + detect() logic + main()-wiring + write_live_state + CLI print), 1 SKILL.md doc edit, 1 new 9-test guard file, 1 targeted pytest run (9/9), 1 broader 24-test regression run, 1 full `-k trendline` repo-wide sweep (86/86, ~404s), 1 curated safety-gate run, 1 RED-proof git-stash round-trip + re-verify, 2nd curated safety-gate run, 2 queue.md edits (item 2 closure + stale T-GYM-20260717 closure), 1 commit — no LLM in the hot path, no orders, PAPER-only, zero trading-path files touched). **Files:** `backtest/autoresearch/trendline_engine.py`, `.claude/skills/trendline-draw/SKILL.md`, `backtest/tests/test_trendline_same_day_tier.py`, `automation/overnight/queue.md`. **Commit:** `8555860`.

> **Autonomy metric (`conductor_outcome.py metric`, 20-fire window):** `trend: "improving"` (cost_per_drained $4.12, net_improvement 17, this fire drained 2 items -- the same-day tier + the stale T-GYM-20260717 closure -- at $3.85, a full closure with 9 new tests and zero regressions). Trend flipped from `regressing` to `improving` since the last recorded fire. `function_latest` still shows 0 enters/fills for trading_day 2026-07-18 (last trading day with data; today 2026-07-20 hasn't opened yet -- expected/correct, not a malfunction signal). **Open for the next fire:** items 3 (zoom-aware drawing, spec small but needs a real-screenshot validation loop) remains in TRENDLINE-FIXES-2026-07-17; `task_scorer.py`'s Active-backlog ranking never surfaces HIGH items (0/34 scored this fire) since HIGH items live in dated sub-sections it doesn't parse -- worth a future fire's attention so `--top` stops perpetually re-suggesting the same J-gated MED item while real HIGH work sits unranked.

---


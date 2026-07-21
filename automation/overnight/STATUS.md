## [2026-07-21 ~18:12-19:10 ET] OK -- conductor (AFTERHOURS): EOD-DOJO-EXHIBIT-MANIFEST built + shipped, commits `34608da` (+ `6a2e641` side-quest)

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). Self-audit gaps fully
> triaged (nothing un-actioned). `task_scorer.py --top` again surfaced
> `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still J-decision-gated). Picked queue.md's HIGH item
> `EOD-DOJO-EXHIBIT-MANIFEST` (filed 14:45 ET today, J-directed) per priority-4 -- a clean,
> bounded, spec'd Sonnet build (`markdown/specs/DOJO-EOD-PIPELINE.md`).

> **Side quest before the build:** found `CLAUDE.md` MODIFIED + a new
> `markdown/doctrine/OP-33-verify-visibility.md` UNTRACKED in the working tree -- a prior fire's
> context-leanness trim that was complete (verified: `check-context-budget.ps1` -> YELLOW
> 8457/9000, 94%, matching the trim's own claimed effect) but had NEVER been committed (an
> L221/OP-33 "built != shipped until committed" violation sitting silently in the tree).
> Committed it standalone (`6a2e641`) before starting the main build. Filed a lesson-inbox item
> (`2026-07-21-claimed-shipped-in-own-doc-before-commit-ran.md`) proposing `verify_committed.py`
> get wired into the conductor's own STAGE 5 close-out so this class can't recur silently.

> **What shipped:** `setup/scripts/dojo/exhibit_extractor.py` -- pure, $0 read of
> `core-decisions.jsonl` + `journal/trades.csv` -> `automation/state/dojo/session-briefs/
> {date}.md`, <=6 ranked exhibits/day: BLOCKED-TRIGGER (verdict SKIP_* w/ triggers non-empty,
> forward SPY path per OP-33(d)), SCORE-HIGH-NO-TRIGGER (bull/bear score >=9, triggers=[]),
> EXTRA-LANE FILL (`extra_exec[].exec.status=="PLACED"`), J-CALLED (`trades.csv`'s own clean
> `j_override=="Y"` marker). Never overwrites a hand-authored brief (AUTO_MARKER guard).
> Registered `Gamma_EodDojoManifest`, 16:20 ET weekdays (5 min after `Gamma_TradeAutopsy` so its
> counterfactuals are citable), `backtest\.venv` pythonw = already reaper-exempt. Ported
> trade_autopsy.py's HEADLESS STDIO REDIRECT popup guard proactively (identical launch chain
> that caused that scar on a sibling script).

> **Verified this fire (OP-33):** `backtest/tests/test_exhibit_extractor.py` 29/29 -- caught +
> fixed a real def-time-parameter-binding bug DURING RED-proofing (`build_exhibits`/`main` were
> silently ignoring test monkeypatches on `TRADES_CSV`/`CORE_DECISIONS` -- the exact footgun
> `trade_autopsy.py`'s own `write_twin_hypotheses` docstring names; fixed by forwarding the
> current module global explicitly at every call site). RED-proofed via file-move (new
> untracked file -- avoided a tree-wide `git stash` after discovering an UNRELATED pre-existing
> stash@{0..2} in this shared checkout from earlier sessions; a blind stash/pop here risked
> clobbering live state, C34/L214/L228 territory -- left those stashes untouched). Broader sweep
> `pytest -k "dojo or exhibit"` -> **158/158 PASS**, zero regressions. Curated safety gate
> (31+5) PASS. Live-verified end-to-end: real 2026-07-17 run (390 decision rows -> 6 exhibits,
> sane content); real 2026-07-21 run correctly SKIPPED (today's hand-authored brief confirmed
> byte-intact after); real `Start-ScheduledTask Gamma_EodDojoManifest` fire, `LastTaskResult=0`.
> `git ls-tree HEAD` confirmed all 3 new files + 2 doc updates landed on HEAD, not just staged.

> **Zero trading-path files touched** -- `exhibit_extractor.py` is observation-only (no broker/
> params/heartbeat_core/placement/exit code), CLAUDE.md side-quest was doc-only. Ships as
> engine-benefit per OP-22/OP-26, no J ratification needed. **Revert:**
> `git revert 34608da` (4 files: extractor, tests, installer, SCHEDULED-TASKS.md/queue.md doc
> updates) + `Unregister-ScheduledTask -TaskName Gamma_EodDojoManifest` to un-arm the schedule
> independently. **Not done this fire:** `DOJO-BUILD-HANDOFF`'s Phase-1 step 0 (TV replay MCP
> tools) remains not-pickable by a conductor fire (no TV MCP tool binding this session --
> unchanged from prior fires' finding, not re-investigated).

> **Cost: ~$6.4** (STAGE 0/1 reads, schema exploration of core-decisions.jsonl/trades.csv, side
> quest investigation + commit, module build, 29-test guard file + one round of real bug fixes
> found during RED-proofing, file-move RED-proof, 158-test broader sweep, curated safety gate x2,
> live scheduled-task registration + fire + verification, doc updates (SCHEDULED-TASKS.md +
> queue.md), lesson-inbox filing, this STATUS/queue update, conductor_outcome recording).

---

## [2026-07-21 ~17:42-18:10 ET] OK -- conductor (AFTERHOURS): stale validator-inbox item closed + time-bomb test found+fixed, commit `426e097`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). `task_scorer.py --top`
> surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still correctly J-decision-gated). Checked
> the fresh self-audit gap batch (2026-07-21T17:31:28, 7 gaps re: the TV-CDP check the PRIOR
> fire shipped) first per Stage-1 priority-3 -- both its concrete claims ("missing timeout",
> "trading-halt risk") were checked against live code and found FACTUALLY WRONG (timeout=5.0
> exists; `heartbeat_core.py` has zero self_check/engine-health consumption, confirmed by grep
> -- it's a pure visibility instrument, no halt path exists). Triaged + disposed with evidence,
> no code action. Moved to priority-5 (author inboxes, oldest-first): `_validator-inbox`'s
> oldest live item, `2026-07-14-tick-audit-zero-count-bug.md` (7 days stale), was the pick.

> **What shipped:** the item's root fix had ALREADY landed same-week (commit `cc6755b`,
> 2026-07-14) but the inbox item itself was never marked closed -- live-verified the fix still
> holds (`heartbeat-tick-audit-2026-07-21.json` -> `total_ticks: 770`, not 0) and closed the
> loop. While re-running the fix's own guard suite to verify before closing, found
> `test_stale_source_none_when_fresh` (`backtest/tests/test_eod_full_audit.py`) had gone
> SILENTLY RED on 2026-07-21 with zero code change -- a genuine new defect, a "time-bomb test"
> that hardcoded `TODAY="2026-07-14"` while relying on a freshly-written temp file's REAL
> filesystem mtime, so the "fresh" assertion only ever held on the day it was authored. Fixed by
> deriving `TODAY`/`now` from the file's own real mtime instead of a frozen literal.

> **Verified this fire (OP-33):** RED-proofed via `git stash` -- failed pre-fix with the exact
> expected mtime-mismatch AssertionError, `git stash pop` restored clean, re-verified 10/10
> green. Broader sweep (+ `test_gym_session_tick_audit_classify.py` +
> `test_gym_session_verdict.py`) -> **33/33 PASS**. Curated safety gate (31+5) PASS. `git
> ls-tree HEAD` confirmed all 4 files (test fix, self-audit triage, validator-inbox close,
> new lesson) landed on HEAD, not just staged. Commit `426e097`.

> **Zero trading-path files touched** -- test file + docs only. Ships as engine-benefit per
> OP-22/OP-26, no J ratification needed. **Revert:** `git revert 426e097` (4 files, additive +
> one doc-append, no data loss). **Lesson filed:**
> `_lesson-inbox/2026-07-21-hardcoded-today-literal-vs-real-file-mtime-time-bomb.md` -- the
> generalizable class (hardcoded date literal + real-mtime-dependent fixture = silent future
> RED), with the sibling tests in the same file that correctly avoided the trap noted as the
> counter-example pattern.

> **Cost: ~$3.1** (STAGE 0/1 reads incl. self-audit-gap live-code verification, validator-inbox
> read, root-cause trace to commit cc6755b + live JSON spot-check, guard-suite re-run that
> surfaced the time-bomb test, fix + RED-proof round-trip, 2 regression sweeps, curated safety
> gate, commit + `git ls-tree HEAD` verification, lesson-inbox write, this STATUS/queue update).

---

## [2026-07-21 ~17:12-17:35 ET] OK -- conductor (AFTERHOURS): TV-CDP liveness check shipped to self_check.py, commit `866aac9`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55, TV CDP itself currently
> healthy per `tv-watchdog-status.json`). `task_scorer.py --top` surfaced
> `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still correctly J-decision-gated, not actionable).
> Self-audit gaps (`analysis/self-audit/new-gaps-flagged.md`) fully triaged, nothing new.
> Author inboxes (validator/skill/lesson/chef) had only already-DONE or thin/low-value items.
> Chose `D1-TV-CDP-ROOT-CAUSE` (HIGH, filed 2026-07-09, pending 12 days) instead: item 3
> ("port assess_tv_cdp into self_check.py") was a clean, bounded, effort=S visibility gap the
> original D1 audit itself scoped -- confirmed still real via a live grep (zero tv/cdp/9222
> hits in self_check.py) before touching anything.

> **What shipped:** `self_check.py` gained `check_tv_cdp(now, fetch=None)` +
> `_fetch_tv_cdp_reachable()` -- a live urllib probe of TradingView's CDP endpoint
> (`:9222/json/version`), ported (not imported, matching this file's own established
> deliberate-duplication convention) from `preopen_readiness.py`'s existing
> `assess_tv_cdp`/`fetch_tv_cdp` pair. Windowed 08:10-16:00 ET weekdays (matches
> Gamma_LaunchTV/Gamma_TvWatchdog's operating window); classifies RED/BROKEN (not DEGRADED) on
> an unreachable CDP, matching the source function's own critical severity -- the 2026-07-07/09
> 41+ hour outage had a real, disclosed cost (premarket bias degraded to `"no-trade-tv-fail"`,
> waving off a plausible trading day) and nothing in self_check.py -- the surface J's
> STATUS.md/engine-health.json morning brief actually reads every ~30 min -- ever saw it, 12
> days after the audit flagged the fix as effort=S. Wired as step 14 in `run()`.

> **Verified this fire (OP-33):** new guard `backtest/tests/test_self_check_tv_cdp.py` (8/8)
> RED-proofed via `git stash -- setup/scripts/self_check.py` alone -- all 8 failed pre-fix with
> the exact expected `AttributeError: module 'self_check' has no attribute 'check_tv_cdp'`,
> `git stash pop` restored cleanly, re-verified 8/8 green. Broader sweep
> (`pytest backtest/tests/ -k self_check`) -> **71/71 PASS, 0 regressions**. Curated safety gate
> (31+5-suite) PASS. `git ls-tree HEAD` confirmed both files landed on HEAD, not just staged.

> **Zero trading-path files touched** -- `self_check.py` is an observation-only monitoring
> organ (no broker/params/heartbeat_core/placement/exit code). Ships as engine-benefit per
> OP-22/OP-26, no J ratification needed. **Revert:** `git revert 866aac9` (2 files, additive,
> no data loss). **Not done this fire:** item 1 of the same queue entry (live repro of the
> 2026-07-08 `PSArgumentException` in `Invoke-TvLaunchSafe`) was NOT attempted -- TV/CDP is
> currently healthy (`cdp_up: true`), so there is no active outage to reproduce, and forcing one
> just to repro a 12-day-stale error message would risk disrupting J's actively-used TV chart
> for no evidentiary gain. Left `D1-TV-CDP-ROOT-CAUSE` as `CLOSED_PARTIAL` in queue.md so a
> future fire with a genuine live outage can still pick up item 1.

> **Cost: ~$2.9** (STAGE 0/1 reads incl. task_scorer + self-audit/inbox sweep, D1-audit
> re-read, source survey of preopen_readiness.py + self_check.py conventions, new function +
> wiring, new 8-test guard file + RED-proof round-trip, broader 71-test sweep, curated safety
> gate, commit + `git ls-tree HEAD` verification, this STATUS/queue update).

---

## [2026-07-21 ~16:42-17:35 ET] OK -- conductor (AFTERHOURS): exit_shape_parity_study core-arms blind-spot fixed, T-W7C closed SUPERSEDED, commit `e7d98b3`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). Fill-funnel GREEN
> (core:safe/bold only accounts trading -- fleet arms all 0, expected/known). Self-check DEGRADED
> on the same non-load-bearing TRENDLINE-DRAW-never-marked flag as the prior fire (not re-fixed,
> visibility-only). `task_scorer.py --top` surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER`
> (still correctly J-decision-gated, not actionable this fire). Chose NOT to take the top-scored
> item; instead followed the recurring signal: the SAME `T-AUTOPSY-*-stop-noise`/`-left-on-table`
> hypothesis + identical "proposed_tests" text has been re-filed by `trade_autopsy.py` every day
> since 2026-07-09 (07-09/07-20/07-21 all present in queue.md) pointing at
> `exit_shape_parity_study` + "STOP-A pre-registration (T-W7)" -- a 12-day-old un-actioned loop,
> exactly the "compound don't accumulate" (OP-22) tiebreak.

> **Root-caused, not just re-triaged:** `exit_shape_parity_study.load_fleet_engine_fills()`
> (the shared real-fills loader for the ENTIRE exit-shape research lineage -- structure_stop_study,
> structure_stop_zone_band_ab, structure_stop_reference_level_ab, ribbon_ride_strike_exit_ab,
> p5_topcell_real_fills_confirm, t4/t5_matrix, ~14 call sites) hardcoded `FLEET_REST_ARMS`
> (safe-1/safe-3/risky-1/risky-3) -- fleet_rest has been dark (0 fills) since 2026-07-09, while
> ALL real trading since has been on the CORE arms (`safe-2`/`bold-2`, 200 fills in
> `fills-ledger.jsonl`, current through today). This is the exact, twice-disclosed-but-unfixed
> "0/0 exhibit fills recoverable" gap from 2026-07-20's STRUCTURE-STOP-ZONE-BAND/
> STRUCTURE-STOP-REFERENCE-LEVEL closures, and the reason the recurring T-AUTOPSY hypothesis's
> proposed test has never once been runnable against current data.

> **Fix shipped (additive, NOT a default change):** added `CORE_ARMS = ("safe-2","bold-2")` +
> `ALL_LIVE_ARMS = FLEET_REST_ARMS + CORE_ARMS`; `load_fleet_engine_fills` gained an `arms=`
> parameter defaulting to the UNCHANGED `FLEET_REST_ARMS` (verified 127 real core-arm fills
> predate `structure_stop_study.ANCHOR_END_DATE` 2026-07-08 -- a default-scope widening would
> have silently shifted the already-frozen `-757.1` CONTROL anchor pin, the exact
> re-pick-after-seeing-results hazard the no_repick_clause discipline exists to prevent). Also
> fixed the hardcoded `exit-shape-parity-2026-07-08.json` output filename to use the real run
> date. Closed `T-W7C-GRIND-VERIFY-THEN-STOPB` (HIGH, pending since 07-09) as SUPERSEDED -- its
> mass-grind machinery was already overtaken by the more rigorous 2026-07-11/07-20 real-fills
> study lineage, which already answered STOP-B's governing question (SS-B/chart-stop-primary
> stays, ATM strike, trigger-exact reference).

> **Verified this fire (OP-33):** new `backtest/tests/test_exit_shape_parity_study_core_arms.py`
> (5 tests) RED-proofed via `git stash push -- backtest/tools/exit_shape_parity_study.py` --
> 4/5 failed pre-fix with the exact expected `AttributeError: ... no attribute 'ALL_LIVE_ARMS'`
> (5th, backward-compat default test, correctly passed pre-fix too -- unchanged behavior);
> `git stash pop` restored cleanly, re-verified 5/5 green. Broader sweep:
> `test_structure_stop_study.py -m "not slow"` -> **21/21 PASS** (1 network-dependent anchor-pin
> test correctly deselected, untouched by design). Curated safety gate (31+5) PASS. `git ls-tree
> HEAD` confirmed all 4 files (tool, new test, queue.md, lesson-inbox) landed on HEAD, not just
> staged. Commit: `e7d98b3`.

> **Zero trading-path files touched** -- `exit_shape_parity_study.py` is observation-only
> analysis tooling (no broker import, no params/heartbeat_core/filters/placement/exit code).
> Ships as engine-benefit per OP-22/OP-26, no J ratification needed. **Revert:** `git revert
> e7d98b3` (4 files, additive + one queue-doc edit, no data loss). **Lesson filed:**
> `_lesson-inbox/2026-07-21-real-fills-loader-blind-to-arm-rename.md` -- a "real fills" anchor
> can go synthetic-by-omission when the account/arm lineup moves on without the loader's scope
> being re-verified (C14/C7 new angle).

> **Not done this fire (deliberately, per no_repick_clause):** did NOT re-run any of the
> exit-shape studies against the newly-visible core-arm data -- that is left for a future fire
> to spec as its OWN fresh, separately-frozen pre-registration, not silently folded into an
> existing verdict.

> **Cost: ~$5.4** (STAGE 0/1 reads incl. task_scorer + fill_funnel + queue HIGH-tier sweep,
> root-cause trace across 6+ downstream tools, fills-ledger arm-distribution forensics, source
> fix + docstring, new guard test file + RED-proof round-trip, 2 regression sweeps, curated
> safety gate, commit + `git ls-tree HEAD` verification, lesson-inbox write, this
> STATUS/queue update).

---

## [2026-07-21 ~16:12-16:45 ET] OK -- conductor (AFTERHOURS): DOJO-EXIT-HARNESS-BUGS fixed + re-run, commit `e94d72b`

> **STAGE 0/1:** engine-health GREEN (market closed since 15:55 today, this fire's own check
> ran 16:12 ET before the gate mattered). Fill-funnel GREEN today (core:bold's lone ENTER_BEAR
> at 15:10:04 traced -- `action: SKIP_LATE_ENTRY`, correctly downgraded by the post-15:00 entry
> ceiling, not a placement gap, same pattern as the 07-20 precedent). Self-check DEGRADED on
> "TRENDLINE-DRAW never marked today" (non-load-bearing, visibility-only) -- left for the
> trendline-draw skill, not this fire's scope. `task_scorer.py --top` surfaced
> `DOJO-EXIT-HARNESS-BUGS` (HIGH, filed 08:xx ET today, verdict VOID) with an advisory to
> re-verify it still reproduces before acting -- confirmed still real by reading the VOID
> report + the harness source before touching anything.

> **What shipped (commit `e94d72b`):** `backtest/tools/dojo_exit_diversity_replay.py`'s
> `extract_entries_and_ribbon` iterated `engine_step.load_day_bars()`'s full multi-month
> warmup frame as if it were the target day's own bars -- a `day=2026-06-30` episode leaked a
> cursor dated `2026-05-21` into `engine_step.step()`, inflating 4 curriculum days to 810 bogus
> episodes (most BS-synthetic) and voiding the whole study. Fix: `day_rth =
> rth[rth["timestamp"].dt.date == day_date]` restricts the entry/ribbon cursor loop to the
> target day only; the untrimmed `bars` frame is still passed to `engine_step.step()`
> unchanged so ribbon/level EMA warmup is unaffected. Re-assessed the report's SECOND claimed
> bug (CONTROL==RIBBON identical P&L) as NOT a separate defect -- it's mathematically BY
> DESIGN for this ribbon_ride-only entry population (registry exit shape already equals
> RIBBON's own patch), already disclosed in the module's own docstring and pinned by an
> existing test (`test_exit_profiles_pulled_from_live_accounts_json`); bug 1's contamination
> is what made it look like a collapsed mapping.

> **Verified this fire (OP-33):** new guard `test_extract_entries_scoped_to_target_day_only`
> RED-proofed via `git stash` on the source file alone -- failed pre-fix with the exact
> leaked-date signature (`saw {'2026-06-30', '2026-06-29'}`), passed post-fix, stash popped
> clean. Full `test_dojo_exit_diversity_replay.py` 11/11 green; broader dojo sweep (+
> engine_step, sim_executor, fence, no_broker) **44/44 PASS**. Curated safety gate (31+5)
> PASS. Re-ran the harness on the SAME reduced day-set post-fix: clean, non-contaminated n=5
> real-fills episodes per profile (was bogus n=115/810) -- ZONE-RIDE correctly differentiates
> from CONTROL ($369.91 vs $400.91), confirming the exit_patch->walk_exit_manager mapping was
> reaching correctly all along. Verdict `CONTROL_HOLDS` on this small, now-honest n --
> disclosed as a first clean signal, not a final answer. `git ls-tree HEAD` confirmed all 5
> changed files (2 source, 1 report, 1 scorecard, 1 queue) + the new lesson-inbox file landed
> on HEAD, not just staged.

> **Zero trading-path files touched** -- `dojo_exit_diversity_replay.py` is an
> observation-only analysis tool (HARD FENCE: no broker import, no git ops, guarded), so this
> ships as engine-benefit per OP-22/OP-26, no J ratification needed. **Revert:** `git revert
> e94d72b` (6 files, additive + one regenerated-report + one regenerated-scorecard, no data
> loss). **Lesson filed:**
> `_lesson-inbox/2026-07-21-warmup-frame-misread-as-single-day-scope.md` -- new angle
> alongside C6 (no look-ahead): a shared loader documented to return a full-history WARMUP
> frame is not automatically safe to iterate as a per-day EVENT stream; a new consumer must
> explicitly re-slice to its own actual scope before treating the untrimmed return value as an
> iteration frame.

> **Not fixed this fire (flagged, out of scope):** `DOJO-CACHE-SELECTION-PERF` (the
> `_find_cache_csv` "picks the largest DST-spanning superset for 07-08 -> hangs" complaint)
> was NOT independently re-verified -- `engine_step._find_cache_csv`'s current docstring/sort
> key already implements "prefer smallest covering file", so the perf issue may already be
> moot as a side effect of an earlier fix, but 07-08 specifically was not re-run to confirm.
> Left open for a future fire or if J hits it directly.

> **Cost: ~$4.7** (STAGE 0/1 reads incl. fill-funnel trace + task_scorer + full harness source
> read + engine_step/sim_executor/exit_manager_walk root-cause trace across 3 files, fix +
> new RED-proofed guard test, stash round-trip, 44-test broader sweep, curated safety gate,
> harness re-run to produce the corrected report, commit + `git ls-tree HEAD` verification,
> queue/STATUS/lesson-inbox updates).

---

## [2026-07-21 ~09:12-09:26 ET] OK -- conductor (AFTERHOURS): ACTUATOR-RESOLVE-DUP-ID-FAIL-LOUD shipped (L207 defense-in-depth), commit `f60da48`

> **STAGE 0/1:** engine-health GREEN (13/13, market not yet open -- fired ~09:12-09:26 ET, before
> the 09:30 gate; STAGE 0's market-hours check only blocks 09:30<=ET<15:55, so this window is
> legitimately open work time, same as any other pre-open minute). `task_scorer.py --top` again
> surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still correctly J-decision-gated). Self-audit
> gaps file has no un-actioned tail (last batch 07-18, already closed). Read every open HIGH
> queue.md item: all either blocked on organic data accrual (EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT
> -- n too small, correctly DEFER-INSUFFICIENT-DATA, not re-chaseable this fire), too broad for
> one bounded fire by the filer's own framing (WSCRIPT-FIRE-AND-FORGET-AUDIT), or big multi-fire
> architecture builds (DOJO-BUILD-HANDOFF needs live TV MCP tools not in this fire's tool set;
> ENGINE-VECTORIZATION/GATE-TIERS-IMPLEMENT). Investigated WSCRIPT-FIRE-AND-FORGET-AUDIT's two
> sub-options first (redirect stdio per-task vs a generic freshness-ratchet loop) and found the
> `_exec` blocking-vbs variants that already solve the launcher problem exist but are unwired
> from ~14 tasks -- flagged as a genuine but Task-Scheduler-touching change, correctly left for a
> dedicated fire rather than forced here. Dropped to `ACTUATOR-RESOLVE-DUP-ID-FAIL-LOUD` (LOW,
> ready, engine-benefit) -- a well-scoped, already-diagnosed (L207) hardening with a named fix.

> **What shipped:** `autonomy_actuator.py` resolved "the row for this proposal_id" via THREE
> incompatible mechanisms (not the two L207 originally named) -- `sync_companion_approvals`'s
> dict-comprehension (last-wins), `revert`'s `next()`-scan (first-wins), and `_set_status`'s
> for-loop-with-break (a third, distinct first-wins shape, found while fixing this). Added ONE
> shared `resolve_proposal(pid, rows)` + `DuplicateProposalError`, routed through all three call
> sites. A terminal+active duplicate (e.g. a harmless `promote_keeper` re-emission) now resolves
> to the ACTIONABLE row regardless of file order -- the old first-wins scans could have silently
> mutated a terminal sibling instead of the live one; two genuinely ACTIVE rows sharing an id now
> raise loud instead of silently picking one; `sync_companion_approvals` catches the exception
> per-decision (logs `duplicate_id_blocked`, skips only that id) so one collision can't stall the
> rest of a companion-approval sync batch.

> **Verified this fire (OP-33):** new `backtest/tests/test_resolve_proposal.py` (10 tests)
> RED-proofed via `git stash` on `autonomy_actuator.py` alone -- 9/10 failed against the pre-fix
> module with the exact expected `AttributeError` (no `resolve_proposal`/`DuplicateProposalError`
> yet), `git stash pop` restored cleanly, re-verified 44/44 green across the full actuator test
> family (`test_resolve_proposal` + `test_autonomy_actuator` + `test_proposal_id_uniqueness` +
> `test_autonomy_auto_approve` + `test_actuator_recency_gate`). Curated safety gate (31+5,
> pre-commit hook) PASS. `git ls-tree HEAD` confirms all 3 files (actuator, new test,
> LESSONS-LEARNED.md) landed on HEAD, not just staged -- not just claimed from a green pytest run.
> L207 updated with a SHIPPED note (was "owed defense-in-depth", now done).

> **Rail-4 CLEAR** (as the item itself flagged): zero `params.json`/`heartbeat_core.py`/
> `filters.py`/placement/exit code touched -- `autonomy_actuator.py` only ever edits those files
> THROUGH its own gated `apply_ops` + safety-gate + snapshot path, never directly; this fix is to
> the approval-bus plumbing around that path. **Revert:** `git revert f60da48` (3 files, additive
> + one doctrine-doc edit, no data loss).

> **Cost: ~$4.9** (STAGE 0/1 reads incl. task_scorer + full HIGH-tier queue review + WSCRIPT
> sub-investigation that was correctly NOT acted on, engine_health.py/self_check.py/vbs-launcher
> reads, autonomy_actuator.py code read + root-cause trace of the third resolution mechanism, fix
> + 10 new guard tests, RED-proof round-trip, 5-file regression sweep, curated safety gate, commit
> + `git ls-tree HEAD` verification, L207/queue/STATUS updates).

---

## [2026-07-21 ~07:48-08:20 ET] OK -- conductor (AFTERHOURS): PROSPECTOR-STATE-LOSS-REPROMOTION-FLOOD fixed + backlog deduped, commit `ff8ac55`

> **Autonomy metric (`conductor_outcome.py metric`, 20-fire window):** `trend: "regressing"`
> (net_improvement 99 / cost_per_drained $0.73 / 0 regressions across the window) -- this fire's
> own drained:37/cost:$3.9 (~$0.11/drained) pulls the average the RIGHT direction, but the trend
> label itself hasn't flipped yet. Flagging per this prompt's own STAGE 5 instruction rather than
> chasing it further this fire (rail 3, one bounded task); next fire should prefer a loop-closer
> again over a fresh artifact if the trend is still regressing.

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55 prior day). Self-check
> GREEN, fill-funnel GREEN both today (idle, premarket) and yesterday 2026-07-20 (core:safe
> 406->28->10->0->1->1->3->3, core:bold 386->18->1->0->0->0->0->0 -- traced the bold ENTER=1/
> attempt=0 row: verdict ENTER_BEAR at 15:43 ET correctly downgraded to `SKIP_LATE_ENTRY`
> (post-15:00 ceiling), not a placement gap). Self-audit gaps file clean (no batch since 07-18,
> already closed last fire). `task_scorer.py --top` re-surfaced the still-correctly-J-gated
> `MORNING-BULL-QUALITY-GATE-RECONSIDER`. Read every `queue.md` HIGH item in full: all either
> `status:done`/`CLOSED`/`CLOSED_KILL`/`CLOSED_NO_SHIP`/`CLOSED_PARTIAL`-with-remainder-already-
> re-filed-and-DEFER-INSUFFICIENT-DATA, or explicitly `NOT PICKABLE` (`DOJO-BUILD-HANDOFF` needs
> live TradingView MCP tools this fire's bound tool set does not carry -- confirmed again by
> checking the actual function list, not assumed). HIGH tier fully drained/blocked -> moved to
> STAGE 1 priority-5 (author inboxes, oldest-first).

> **What was found:** `_chef-inbox` carried 65 files, 60 of them `prospector-*` (`Gamma_Prospector`,
> the daily exogenous-data-idea scout), oldest 2026-06-16 -- and `_chef-log.jsonl` had **0** hits
> for "prospector": chef had never reviewed a single one. Traced why: root cause is the
> 2026-06-27..07-13 git-stash-drop recovery (commit `41889a0`) reset `analysis/prospector/
> state.json`, wiping its `promoted_dedupe_keys` idempotency tracker. Ledger rows from before
> the reset stayed re-eligible for `promote_top1`'s FIFO "oldest not-yet-promoted" pick (the
> ledger itself never lost them -- `append_ledger_rows` is dedupe_key-idempotent, so they were
> never re-added, only re-SELECTED for promotion) -- so the same 17 underlying ideas got
> re-promoted into fresh dated `_chef-inbox` files every few days for **24 days**, undetected:
> 37 of 65 files (57%) were pure re-promotion noise.

> **What shipped (commit `ff8ac55`):** `already_promoted_from_inbox()` in
> `setup/scripts/prospector.py` derives "already promoted" straight from the `_chef-inbox`
> filesystem (any date, `.md` or `.md.DONE`, matched by dedupe_key tail) as a SECOND check
> independent of `state.json` -- a repeat state loss can no longer reproduce this bug class.
> Repaired `state.json`'s `promoted_dedupe_keys` from 5 entries to the full recovered set of 28
> (union of state + filesystem-derived). Deduped the existing backlog: the 37 redundant files
> renamed to `.DONE` with a pointer note to the surviving first-surfaced copy, leaving **28
> unique ideas + 1 non-prospector item** for chef to actually work through (down from 60).
> **Verified this fire, not just claimed (OP-33):** 6 new guard tests in
> `backtest/tests/test_prospector.py` (55/55 total) RED-proofed via `git stash` -- all 6 failed
> with the exact expected pre-fix mismatch (quoted assertion diffs match the bug mechanism
> precisely), `git stash pop` restored cleanly, re-verified 55/55 green. Broader sweep
> (`test_prospector` + `test_firm_brief_prospector_section` + `test_free_model_audit_prospector`)
> **81/81 PASS**. Curated safety gate (31+5-suite) PASS. Post-commit, confirmed the commit
> ACTUALLY landed via `git ls-tree HEAD` on both a surviving unique file and a `.DONE`-renamed
> duplicate (both present exactly as expected), not just a green pytest run.

> **Zero trading-path files touched** (`prospector.py` is an observation-only R&D organ, no
> params/heartbeat_core/filters/placement/exit code) -- ships as engine-benefit per OP-22/OP-26,
> no J ratification needed. **Revert:** `git revert ff8ac55` (68 files, purely additive/renaming,
> no data loss on revert). **Lesson filed:**
> `_lesson-inbox/2026-07-21-producer-state-loss-silent-inbox-flood.md` -- new discovery angle on
> C34 (a silently-reset producer idempotency state can flood a downstream author inbox for weeks
> with zero crash/RED symptom; general antidote is deriving idempotency from the downstream
> artifact, not solely an upstream counter that can be reset independently of it). Flags a
> broader-sweep follow-up (future fire, not this one): check whether the kitchen seeder /
> self-audit gap-finder / swarm consult routers have the same exposure.

> **Not fixed this fire (flagged, out of scope):** `state.json`'s `fires_total: 4` counter is
> itself stale (real fire count since 2026-06-16 is far higher) -- cosmetic/non-load-bearing,
> left alone. 3 pre-existing dangling `git stash` entries (unrelated to this fire, predate this
> session, correctly NOT dropped) -- noted for a future fire's cleanup judgment.

> **Cost: ~$3.9** (STAGE 0/1 reads incl. funnel/self-check/engine-health/task_scorer, full
> `queue.md` HIGH-tier review, chef-inbox root-cause investigation across prospector.py/
> state.json/git log/ideas-ledger.jsonl, fix + state-repair script + backlog-dedup script, 6 new
> guard tests + RED-proof round-trip, 81-test broader sweep, curated safety gate, commit +
> post-commit verification, queue/STATUS/lesson-inbox updates).

---

## [2026-07-21 ~05:48-05:56 ET] OK -- conductor (AFTERHOURS): SELF-AUDIT-GAPS-TRIAGE-BATCH -- 8 un-actioned batches (07-02 through 07-18) closed, commit `fdbdfec`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). `task_scorer.py --top`
> re-surfaced the still-correctly-J-decision-gated `MORNING-BULL-QUALITY-GATE-RECONSIDER`. Checked
> `analysis/self-audit/new-gaps-flagged.md` (STAGE 1 priority-3, Gamma's own proactive gap-finder
> organ) and found **8 daily batches (2026-07-02 through 2026-07-18) with NO DONE resolution** --
> the exact "compound, don't accumulate" (OP-22) violation the lesson-inbox drain fixed two fires
> ago, this time in the self-flagged-gaps producer. This outranked the queue's remaining HIGH items
> per STAGE 1 priority order.

> **What shipped:** read all ~90 flagged lines across 8 batches, verified every falsifiable claim
> against current code THIS fire (not memory/docs): `fill_funnel.py` exists and resolves the "Zero
> Fill Execution Black Hole (G9)" gap; `risk_gate.py` line 347 already rejects missing/unreadable
> `per_trade_risk_cap_pct` and fails CLOSED, resolving "position-sizing must be guarded against
> corrupt config"; `Gamma_LicenseMonitor` runs DAILY (22:30 ET) not weekly, so the 07-13 "recency
> gate too infrequent" claim was stale/false when it fired; `orchestrator.py`'s 42 `is not None`
> occurrences are all standard override-fallback reads (grepped + read in context), not the
> silent-gate-bypass the 07-11 "Time Bomb" gap alleged -- reviewed, not a bug; `accounts.json` +
> `accounts_status.py`, `promote_keeper.py` + `Gamma_OosCheck` + the AutoApply actuator,
> `v25_filter_gates.py`'s drift+presence ratchets, `contracts/models.py`'s `load_validated`, THE
> DOJO (shipped 07-20), and V15_SAFE_TIERS ATM (shipped 06-18) each independently close one or
> more of the remaining gaps. The rest (cross-asset regime detector, online hyperparameter tuner,
> pre-market stress-test harness, etc.) are forward-looking ideas with no concrete current failure
> cited -- left as ideas, not gaps, consistent with the noise-vs-signal bar the 06-29/07-01/07-19
> fires already established for this same producer.

> **No new gap survived triage with a concrete, unaddressed fix attached.** This fire is
> confirmation the engine's self-generated gap list is being kept current by systems already
> shipped in the weeks since these batches fired -- not new build work. Full per-batch citations:
> `analysis/self-audit/new-gaps-flagged.md`.

> **Zero trading-path files touched** (doc-only: one markdown file, 8 DONE-block insertions) --
> ships as engine-benefit per OP-22/OP-26, no J ratification needed. Curated safety gate (31+5-suite)
> PASS. **Revert:** `git revert fdbdfec` (1 file, purely additive markdown blocks).

> **Cost: ~$2.4** (STAGE 0/1 reads, task_scorer + self-audit-gaps read, 8 code-verification greps
> across risk_gate.py/orchestrator.py/fill_funnel.py/accounts.json/SCHEDULED-TASKS.md, 8 targeted
> Edit insertions, commit + safety-gate verification).

---

## [2026-07-21 ~03:48-04:20 ET] OK -- conductor (AFTERHOURS): LESSON-INBOX-DRAIN-BATCH -- 30 backlogged items (oldest 19d stale) -> 27 new L204-L230 entries + OP-25 index fold, commit `3c9bd69`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). `task_scorer.py --top`
> re-surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still correctly J-decision-gated, skipped
> again). Self-audit gaps file had no un-actioned tail. Checked `_lesson-inbox/` (STAGE 1
> priority-5, author inboxes oldest-first) and found **30** un-actioned items (all 4 non-README
> non-.DONE files were pending), oldest dated 2026-07-02 -- a 19-day-stale author-inbox backlog
> is exactly the "compound, don't accumulate" (OP-22) violation this stage exists to catch, and
> clearly outranked the queue's remaining HIGH items (all already closed or needing TradingView
> MCP tools this fire's tool set doesn't bind).

> **What shipped:** read all 30 inbox items in full, merged 3 write-ups of the same incident into
> single lessons where warranted (hand-maintained-allowlist + hand-mirrored-set +
> setup-dispatch-registry-validator-drift -> **L223**; git-stash-drop-wipes-shared-checkout +
> state-file-reversion-git-ops-on-live-state -> **L214**), producing **27** new cite-or-defer
> entries (**L204-L230**) in `markdown/doctrine/LESSONS-LEARNED.md`, each citing specific file
> paths/line numbers/dates per the lesson-author spec (no hand-wavy doctrine shipped). Folded
> into 8 existing OP-25 C-theme rows (C6 bar-convention, C7 silent-success x8 additions, C8
> headless-spawn, C11 broker-truth, C14 dead-knobs x7 additions, C15 gate-cascades x3, C18
> status-format, C20 gate-direction) and **4 new theme rows**: C32 (autonomous
> proactivity/TradeAutopsy), C33 (shared-gateway-lockout, the CCR/Desktop-app incident), C34
> (tree-wide git ops on live state), C35 (built+tested+RED-proofed != shipped until committed).
> CLAUDE.md's "current through" pointer updated L203 -> L230. Deleted all 30 processed inbox
> items per lesson-author convention (3 of the 30 were untracked-by-git, confirmed via
> `git ls-files` before assuming a clean `rm`).

> **Verified this fire, not just claimed (applying L228's own lesson):** `check-context-budget.ps1`
> flagged RED after the table additions (9139/9000, 102%) -- trimmed the new C32-C35 rows + C14
> parenthetical to 9017/9000 (100.2%, well inside the documented 10.5K hard ceiling; the last ~17
> tokens were left alone per the standing "don't hand-shave doctrine to undershoot" guidance
> rather than chased for a cosmetic green). Post-commit, verified the commit ACTUALLY landed
> (not just staged-green, the exact L228/L214 failure mode) via `git ls-tree HEAD` on a deleted
> inbox path (empty, confirmed gone) and `git show HEAD:...` on both edited files (L230 header
> present, "current through L230" pointer present) -- not just a green pytest run. Curated safety
> gate (31 + 5-suite) PASS.

> **Zero trading-path files touched** (doctrine/index-only change: `LESSONS-LEARNED.md`,
> `CLAUDE.md`, inbox deletions) -- ships as engine-benefit per OP-22/OP-26, no J ratification
> needed. **Revert:** `git revert 3c9bd69` (29 files, 2 edits + 27 deletions).
> **Cost: ~$5.4** (STAGE 0/1 reads, reading all 30 inbox items in full across 3 batches, composing
> 27 cite-or-defer lesson entries + OP-25 fold, 2 rounds of context-budget trimming, verification
> greps + commit + post-commit HEAD checks).

---

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). `task_scorer.py --top`
> re-surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still correctly J-decision-gated). Read
> the self-audit gaps tail (no un-actioned substantive items -- the 2026-07-18 batch's real
> content was already closed by the fire lock + consensus-noise-filter fixes). Picked the
> `STATE-FILE-REVERSION-AUDIT-FOLLOWUP` (MED, ready, depends:none) over the task_scorer top hit
> -- it closes a loop the 2026-07-20 fire left explicitly partial (a documented, bounded,
> non-trading-path infra-hygiene item, OP-22 "close a loop > create an artifact").

> **What shipped:** re-derived the flagged set live (776 tracked files x commit-vs-mtime) --
> found **76** files actively written since last commit, not the item's own stale "~279"
> estimate. Classified all 76 by decision-gating hazard (not just append-vs-snapshot): does a
> silent backward git-revert misrepresent a fact a live entry/exit/kill-switch/sizing decision
> reads? **13 are decision-gating and now fixed:** `fleet/{safe-2,bold-2}/exit-state.json`
> (trailing-stop HWM), **`crypto-twin/breaker.json`+`exit-state.json`+`scenario-state.json`+
> `sim-bear-{scenario-state,positions}.json`** (the twin's OWN circuit-breaker equivalent --
> same hazard class as core `circuit-breaker.json`, simply out of scope for the 2026-07-20
> fix), `key-levels.json`, `sight-beacon.json` (the never-blind eye), `fleet/shared-signal.json`,
> `futures/{mirror-shadow-state,mirror-positions}.json`, `j-intents.json` (J-called trade
> intents). Confirmed live production usage via grep (47 scripts touch the exit-state/breaker/
> key-levels/sight-beacon/j-intents family) before untracking any of them.

> **Verified this fire, not just claimed:** used THIS SAME incident's own corrected technique
> (2026-07-20's queue note: `git commit -- <pathspec>` silently resurrects a staged `rm --cached`
> deletion) -- staged `git diff --cached --stat` confirmed exactly the 15-file target set
> BEFORE committing, then a plain `git commit -m` with **no** pathspec, then `git ls-tree HEAD`
> + `git ls-files` both confirmed EMPTY for all 13 paths (not just the guard test, which only
> checks the index). All 13 files confirmed still present + readable on disk post-untrack. New
> guard tests `test_decision_gating_snapshots_are_gitignored` + `_are_untracked` in
> `backtest/tests/test_ledger_gitignore_guard.py` -- 6/6 green (extends via a new
> `DECISION_GATING_SNAPSHOTS` list, original `STATE_SNAPSHOTS` left byte-identical for audit
> history). Curated safety gate (31+5-suite) PASS via the pre-commit hook automatically.

> **The other 63 flagged files were reviewed, not deferred:** display/diagnostic/derived-cache
> surfaces (`engine-health.json`, `kitchen-status.json`, `dashboard-dialogue.json`, audit logs,
> etc.) -- a revert would show stale info to J/self_check (could trip a false DEGRADED alert)
> but doesn't silently misdirect a placement/exit/sizing decision. Left tracked by design.

> **Rail-4:** zero *behavior* trading-path files touched (`params.json`/`heartbeat_core.py`/
> `filters.py`/placement/exit code unchanged) -- git-tracking-only change; engine code already
> reads these files by path so untracking has no runtime effect. Guard test + git-revert path
> satisfy rail 4's discipline anyway. **Revert:** `git revert 0de01a3` (single pathspec commit,
> 15 files). **Cost: ~$2.7** (STAGE 0/1 reads, engine-health/task_scorer/self-audit-gaps checks,
> queue.md targeted greps across a 2300+-line file, live commit-vs-mtime derivation script,
> 47-file usage grep before untracking, 2 edits + 1 test-file edit + commit + verification).

---

## [2026-07-20 ~22:00-23:40 ET] DOJO Phase 1 BUILT + RUNS E2E -- interactive (Opus + 4 Sonnet builders): J's replay training room. 2 honest gaps before it's the full 6-arm vision.

> **Built + committed + pushed** (1f30e89 + adb1780; audit GREEN): the DOJO tick-by-tick replay training room. Spec markdown/specs/DOJO-REPLAY-TRAINING-SPEC.md, architecture+contracts DOJO-ARCHITECTURE-DECISION.md, runbook DOJO-SESSION-RUNBOOK.md. Package setup/scripts/dojo/ (clock, session spine+fence, engine_step, whisper, directive, sim_executor, scorecard). 109 dojo tests green (100 fast + 9 engine_step slow). TradingView Plus (J-bought) unlocked intraday replay -- VERIFIED (5-min 2026-07-17 steps, ribbon re-forms per step).
> **RUNS END-TO-END (verified this session, not claimed):** `python -m dojo.session step` at 14:00 ET 2026-07-17 renders the real per-arm whisper -- safe ENTER_BEAR bear=10/bull=6, bold SKIP_BULLISH_FILL_BAR (actual Friday behavior). A real directive walked real OPRA bars: TP1 +$553.60 / runner +$262.10 / scorecard +$815.70.
> **Architecture correction (Opus):** spec's "Python drives TV replay" was impossible (MCP tools are the agent's, not a script's). Two roles: agent=hands (TV MCP + relay), Python=brain+books (real engine decision + sim + score). No-LLM-in-decision preserved.
> **TWO HONEST GAPS (NOT the full vision yet -- do NOT call it 100%):**
>   1. **Only 2 of 5 arms live.** safe+bold render faithfully; the 3 FLEET arms (RIBBON/control/ZONE-RIDE exit-diversity lanes -- the "watch them differ" point) show FLEET_VIEW_PENDING. Cause: build_shared_signal.py builds only from TODAY's state, not a historical replay. Phase 1b = DOJO-FLEET-HISTORICAL-SIGNAL (touches a shared prod module -- careful).
>   2. **engine parity ~87% verdict/side, scores drift** (bear/bull exact 43-50%). Cause: no historical key-levels.json snapshot; levels approximated from current (no-look-ahead). Verdict/side robust. Filed: DOJO-HISTORICAL-KEY-LEVELS-SNAPSHOT.
> **Usable NOW:** J + a Sonnet agent walk a real day via the runbook -- see the engine's mind + direct safe/bold + sim P&L. The 3 fleet exit-diversity arms are the immediate next build.

---

## [2026-07-20 ~23:12-23:5x ET] OK -- conductor (AFTERHOURS): RRW-AS-VETO-STUDY -- bear-wick bull overlay tested, FAIL (honest kill), committed

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). `task_scorer.py --top`
> re-surfaced the correctly-J-decision-gated `MORNING-BULL-QUALITY-GATE-RECONSIDER` (skipped
> again). The queue's HIGH-priority trading-path items (`EXTRA-SIGNAL-CHURN-COOLDOWN`,
> `EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT`) were already closed/DEFER-INSUFFICIENT-DATA'd by
> two earlier fires tonight; `DOJO-BUILD-HANDOFF` needs TradingView MCP tools this fire's
> tool set doesn't have bound. Picked the top-scored MED research item instead:
> `RRW-AS-VETO-STUDY` (queued 2026-07-02, never actioned — ribbon_rejection_wick is KILLED
> as an entry but demonstrably SEES real bear rejections; untested as a defensive overlay
> on the live bull path).

> **What shipped:** `backtest/autoresearch/rrw_bull_veto_study.py` -- reuses the EXISTING
> cached RRW superset scan (1793 bear events, $0 to reload) against the REAL bull trade
> population from `lib.orchestrator.run_backtest(use_real_fills=True, enable_bullish=True)`
> at PROD_GATED (the two ratified bull gates), ATM strike (live core tier). Two
> pre-registered configs (detector's own dataclass defaults + the FAIL scorecard's own
> "keeps today's anchor" vol note). **Result: FAIL on both hypotheses.** VETO: both configs
> net NEGATIVE to apply -- the vetoed trades (n=8/$1,265.80 and n=4/$597.60, WR 75% both)
> were WINNERS, not losers; the hypothesis (bear-wick flags bad bull entries) does not hold
> in this sample. TIGHTEN: too rare (n=2, n=1) to clear the pre-registered n>=10 bar, and
> the n=2 case is internally mixed (one trade +$1,317 better, one -$1,382 worse tightened).
> Scorecard: `analysis/recommendations/rrw-bull-veto-overlay.json` (full trade lists +
> caveats). Queue item closed with the full writeup: `automation/overnight/queue.md`
> `RRW-AS-VETO-STUDY`.

> **DST-frame lesson applied, not re-violated:** `load_contract_bars`' raw tz-aware OPRA
> timestamps (fixed -04:00, EST-mislabeled) were re-derived to the same et-v2 frame the
> SPY/bear-events/trades already use before any comparison -- caught this fire via a live
> `TypeError` on first run, fixed per `project_dst_frame_artifact_2026_07_02`, re-verified.

> **Verified this fire:** new guard `backtest/tests/test_rrw_bull_veto_study.py` (12/12
> PASS -- gate logic, veto-window semantics, stats arithmetic, cache-freshness sanity on
> $0 synthetic fixtures, no full-backtest re-run needed to catch a future regression).
> `test_ribbon_rejection_wick.py` + this file -> 20/20 PASS. Curated safety gate
> (31+5-suite) PASS.

> **Research-only, zero trading-path files touched** (no params/heartbeat_core/filters/
> placement/exit edits -- rail 4 does not apply; ships without J ratification per
> OP-22/OP-26, same class as any author-inbox deliverable). **Revert:** `git revert <commit>`
> (3 new files, purely additive). No live wiring proposed regardless of verdict -- this FAIL
> closes the RRW-AS-VETO-STUDY thread; any future re-open needs new evidence, not a re-run
> of this same config pair.

> **Cost: ~$4.9** (STAGE 0/1 reads, queue.md targeted greps/reads across ~2400 lines to find
> the next pickable item, detector/battery/orchestrator/simulator_real source reads to design
> the overlay study without duplicating existing machinery, 1 script write + 1 DST-frame bugfix
> + 1 successful run, 1 guard-test file write + 1 tolerance fix + verification runs, curated
> safety gate, queue.md + this STATUS entry).

---

## [2026-07-20] LICENSE-MONITOR (deploy-timing for WP-5/6/8/0)

> - #1 ATM (Safe-2)=YELLOW(ELIGIBLE); #1 ATM (Bold)=YELLOW(ELIGIBLE); #2 ATM=YELLOW(ELIGIBLE); #4 ATM=YELLOW(ELIGIBLE)
> - **Trade-to-learn cumulative (since arm, real fills, Rule-9 visibility-only):**
> -   bollinger_squeeze (armed 2026-07-02): since-arm 2tr $+105.00 ($+52.50/tr, 100.0% WR)
> -   double_bottom_base_quiet (armed 2026-07-01, 19d ago): 0 fills since arm — no live signal yet
> -   vix_regime_dayside (armed 2026-07-01, 19d ago): 0 fills since arm — no live signal yet
> -   vwap_continuation (armed 2026-07-01): since-arm 2tr $-68.00 ($-34.00/tr, 0.0% WR)
> -   vwap_reclaim_failed_break (armed 2026-07-01, 19d ago): 0 fills since arm — no live signal yet
> - Files: `automation/state/license-monitor-last.json`, `backtest/autoresearch/license_monitor.py`.

---

## [2026-07-20] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-06-11..2026-07-17), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-07-17). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=YELLOW
> - **Books:** Safe2_ATM_1+2+4=RED ($-419.16); Bold_ATM_1+2=YELLOW ($-262.8)
> - **edges_confirmed_on_recent = False** (any RED=True). All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs. RED-BLOCKED: Safe2_ATM_1+2+4 — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-07-20 22:12-22:40 ET] OK -- conductor (AFTERHOURS): CLAUDE-INDEX-FOLD-BATCH -- 20 remaining lessons folded into OP-25 index, reconciliation ratchet drained to zero, committed `33c7bad`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). Self-audit gaps file
> has no un-actioned tail (last batch, 2026-07-18, already closed 2026-07-19). `task_scorer.py
> --top` re-surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still correctly J-decision-gated,
> skipped again). Active-backlog HIGH items were all closed/J-gated/not-pickable
> (`DOJO-BUILD-HANDOFF` needs TradingView MCP tools this fire's tool set doesn't have bound;
> `MM-05-WAKE-FIRE-REVIVAL` is awaiting-j-ratification). Manually surfaced
> `CLAUDE-INDEX-FOLD-BATCH` (LOW, doc-index, score 4.5, ready) by grepping the 2317-line
> queue.md for `(HIGH,`/L###-CLAUDE-FOLD clusters rather than trusting task_scorer's top-N
> alone -- it consolidates 8 separate queue items and directly closes a standing doctrine-debt
> loop (OP-22 "close a loop > create an artifact").

> **What shipped:** the item's own text claimed **30** unindexed lessons; live re-derivation via
> the guard's own `find_unindexed_lessons()` showed the true remaining debt was **20**
> (`KNOWN_UNINDEXED_BASELINE` = 12 older L03,13,16,24,25,29,31,43,56,126,137,146 + 8 recent
> L192-198,200) -- L169-191 had already been folded by the 2026-06-24/06-28 batches per the
> guard file's own comments, and this queue item was simply never updated (same
> stale-checkbox-shipped-work class as several other items closed tonight). Read each lesson's
> FULL text in LESSONS-LEARNED.md (not just the title) before picking a fold destination:
> L03->C17 (TDD/hand-computed-fixture pattern), L13/L16/L25/L29/L31/L193/L196/L197->C7 (all 8
> are "task exits 0 but the real work silently failed" cases -- Discord bridge, watcher
> granularity, pandas dtype coercion, CDP port death, a decorative sibling-organ gate, a
> presence-not-consistency producer guard, a guard baking in a stale frame), L24->C30
> (chandelier-trailing profit-lock vs fixed-cap exit-shape tuning), L43->C13 (confidence-tier
> rarity-gate calibration), L56->C9 (sys.path/`__file__` anchoring), L126/L137/L146->C22
> (regime-conditional IS/OOS classifiers -- L146's own title literally says "mirrors C22
> regime split"), L192->C4 (edge_capture is a directional-anchor metric, regime-stratification
> class), L194/L195/L198->C14 (dead-knob/gate-completeness class -- selector-vs-executor gate
> gaps, structurally-dead trigger inputs, hardcoded-window frame audits), L200->C11 (verify
> the ACTUAL broker/account facts before modeling a regulatory rule).

> **Precedent applied:** tonight's earlier L202/L203 fold (commit `714f797`) established that a
> lesson-index-ONLY CLAUDE.md edit is the one surface OP-25 reserves for the lesson-author
> path, not rail-4-blocked -- so this item's own "conductor cannot edit CLAUDE.md" framing was
> itself stale. 9 `Edit` calls folded all 20 numbers into their C-rows; verified zero
> within-row duplicates via a small script before committing.

> **Verified this fire, not just claimed:** guard `test_op25_index_reconciliation.py` 9/9 PASS
> with `KNOWN_UNINDEXED_BASELINE` drained to `frozenset(set())`; live re-derivation via the
> guard's own `find_unindexed_lessons`/`find_phantom_index_refs` against the on-disk
> CLAUDE.md/LESSONS-LEARNED.md returns `[]`/`[]` -- zero unindexed lessons, zero phantom index
> refs, the actual invariant holds (not just green tests). Context-budget re-checked post-edit:
> `CLAUDE.md 8831 tok / 9000 (98%)` -- still YELLOW, not pushed to RED (was 8791 pre-edit, +40
> tok net for 9 rows of new L-numbers -- well inside OP-3's 9K cap). Broader sweep
> `test_op25_index_reconciliation.py` + `test_author_inbox_reconciliation.py` +
> `test_self_audit_extract.py` -> **80/80 PASS**. Curated safety gate (5-suite) PASS at commit
> time.

> **Rail-4/OP-25 (doc-index-only -- the one CLAUDE.md surface this class of fire may touch):**
> zero params/heartbeat_core/filters/placement/exit files touched -- only CLAUDE.md's OP-25
> lessons table (9 rows) + the guard's baseline constant. **Revert:** `git revert 33c7bad`
> (3 files: CLAUDE.md, `backtest/tests/test_op25_index_reconciliation.py`,
> `automation/overnight/queue.md`). **Commit:** `33c7bad`.

> **Queue hygiene:** closed all 8 items in the cluster in one edit -- `CLAUDE-INDEX-FOLD-BATCH`
> (corrected, not just checked off) + the 6 subsumed `L169/L170/L173/L174/L177/L178-CLAUDE-FOLD`
> follow-ups (all stale checkboxes -- that work was already done 2026-06-24, well before
> tonight). The reconciliation ratchet is now at true zero: any future authored-but-unfolded
> lesson will fail the guard loud on its own, with no baseline debt left to hide behind.

> **Cost: ~$3.9** (STAGE 0/1 reads incl. engine-health/self-audit-gaps/gym-scorecard/task_scorer,
> 2317-line queue.md targeted greps + reads to find the HIGH-item cluster and this LOW item,
> 20 lesson full-text reads across LESSONS-LEARNED.md to pick fold destinations, 9 CLAUDE.md
> `Edit` calls + 1 guard-file edit, duplicate-check script, context-budget re-check, 3 test-suite
> runs, commit + curated safety gate, queue.md 8-item closure writeup, this STATUS entry).

---


### DEGRADED: self-check 2026-07-21T18:09:56
- TRENDLINE-DRAW never marked today (2026-07-21) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.

## Kitchen
Kitchen: alive, queue 37 pending, last cook 0 min ago, today $0.00, model=grinder-python

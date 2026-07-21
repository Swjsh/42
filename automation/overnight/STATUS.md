## [2026-07-20 20:15-20:45 ET] OK -- conductor (AFTERHOURS): BROKER-CANARY-SENTINEL-HOOKUP -- one-line wiring shipped, guard-tested, committed `3332454`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 18:19+). Fill-funnel priority-1
> check GREEN (1176 ticks, 11 ENTER, 1 attempt/1 accept/3 fills safe, no funnel break). Self-audit
> gaps fully actioned through the 07-19 batch. All queue.md HIGH items already CLOSED tonight by
> prior fires (`DECISION-ROW-SPY-STALENESS`, `STRUCTURE-STOP-ZONE-BAND`, `STRUCTURE-STOP-
> REFERENCE-LEVEL`, `EXTRA-SIGNAL-CHURN-COOLDOWN` item 1, `PREMARKET-TOUCH-CREDIT-STUDY`); the
> remaining MED items (`EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT`, `STRIKE-TIER-RECONCILIATION-
> FOLLOWUP`, `PROFIT-P2-ARMED`) are all correctly `pending`/`DEFER-INSUFFICIENT-DATA`/`forward-
> watch` -- genuinely blocked on more organic data or a J doctrine decision, not pickable this
> fire. `task_scorer.py --top` re-flagged the J-decision-gated `MORNING-BULL-QUALITY-GATE-
> RECONSIDER` (correctly re-skipped again). Picked `BROKER-CANARY-SENTINEL-HOOKUP` (LOW,
> "ready-for-one-line-wire" since 2026-07-11) -- closes a real 9-day-old loop (a fully-built,
> live-verified module sitting completely unwired) over creating a new artifact, and is a
> genuinely bounded, low-risk task matching this fire's remaining scope.

> **What shipped:** `setup/scripts/broker_canary.py`'s `probe()` was built + live-verified
> 2026-07-11 but had zero scheduled-task hookup -- `preopen_readiness.py`'s `broker_canary`
> check could only ever see a stale/absent file until someone ran the CLI by hand. Wired the
> one-line call (`import broker_canary as bc` + `bc.probe()`) into `crypto_twin_health.main()`
> -- the CLI entrypoint `Gamma_CryptoTwin`'s scheduled task invokes every 5 min, 24/7 -- rather
> than into `run_tick_with_health()`, deliberately: that function has 34 existing tests with
> zero network mocking, and `probe()`'s leg 1 (unauthenticated crypto bars) is a REAL HTTP call;
> wiring it there would have made the whole existing suite silently network-dependent. `main()`
> had zero prior coverage, so this is a strictly additive change with no blast radius to an
> already-tested surface. Belt-and-suspenders `try/except` at the call site on top of `probe()`'s
> own internal fail-open guarantee -- a canary failure can never change the tick's own exit code
> or logged action.

> **Verified this fire:** 2 new tests RED-proofed via `git stash` on both files -- both failed
> with the exact expected `AttributeError: module 'crypto_twin_health' has no attribute 'bc'`
> with the wiring removed, `stash pop` restored cleanly, re-verified 34/34 green in
> `test_crypto_twin_health.py` (0.23s -- confirms zero accidental real network calls leaked into
> the mocked tests). Broader sweep `test_crypto_twin_health.py` + `test_broker_canary.py` ->
> **72/72 PASS**. Cross-checked `test_preopen_readiness.py`'s 1 pre-existing failure
> (`test_fetch_eod_flatten_reality_reads_real_tmp_files`, `KeyError: 'Gamma_EodFlatten'`) is
> unrelated and pre-existing -- reproduces identically with both my files stashed out, confirmed
> before closing this item as clean. Curated safety gate (31+5-suite) PASS.

> **Rail-4 (PAPER/visibility-only -- guard test + revert path + this REVOKE report).** Change:
> `setup/scripts/crypto_twin_health.py` (additive: 1 new import, 1 new try/except block in
> `main()`, 1 new key in the printed JSON) + `backtest/tests/test_crypto_twin_health.py` (2 new
> tests). Zero `params.json`/`heartbeat_core.py`/`filters.py`/placement/exit code touched -- this
> is observability, not a capital decision; the canary can never place an order or change any
> trading behavior. **Revert:** `git revert 3332454` (2 files, clean no-behavior-change rollback
> -- the twin's tick and `preopen_readiness.py`'s existing fail-open handling of a stale canary
> file are both unaffected either way). **Commit:** `3332454`.

> **Cost: ~$2.9** (STAGE 0/1 reads incl. engine-health/STATUS/queue/self-audit/fill-funnel/
> task_scorer, queue.md targeted offset reads (2200-line file), module read + wiring-site
> survey, edit, 2 new tests, 2 RED-proof round trips via git stash, 1 broader 72-test
> regression sweep, 1 curated safety gate run, 1 commit, this queue/STATUS update). **Files:**
> `setup/scripts/crypto_twin_health.py`, `backtest/tests/test_crypto_twin_health.py`,
> `automation/overnight/queue.md`.

---

## [2026-07-20 19:42-19:50 ET] OK -- conductor (AFTERHOURS): STATE-FILE-REVERSION-2026-07-20 -- untracked circuit-breaker*.json + today-bias.json (git-ops-reverts-live-state bug), CLOSED_PARTIAL, committed

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). Fill-funnel priority-1
> check GREEN (406/386 core ticks, 1 attempt/1 accept/3 fills safe, no funnel break). No new
> self-audit gap batch today. `task_scorer.py --top` returned the already-repeatedly-skipped
> J-decision-gated `MORNING-BULL-QUALITY-GATE-RECONSIDER`. Top of queue.md's HIGH backlog: the
> filed-but-unactioned `STATE-FILE-REVERSION-2026-07-20` (real, twice-reproduced-today infra
> bug, outranks that J-gated item and every routine MED/LOW item) -- picked it.

> **Verified the bug is live, not stale:** `git ls-files` confirmed circuit-breaker.json (both
> core accounts + 4 fleet arms) and today-bias.json (main + futures) were STILL tracked, last
> committed 2026-07-14, with mtimes as recent as tonight 17:43 ET -- exactly the
> tracked-but-rarely-committed danger signature that let a `git stash`/`checkout` in the shared
> checkout silently revert live kill-switch/bias state BACKWARD (reproduced twice today per the
> queue item: 04:27/05:58 ET premarket + 18:40 ET mid-session). Same root-cause CLASS as the
> 2026-07-14 decision-ledger stash-drop incident (commit 41889a0), recurring on a different file
> class because that fix treated the symptom (4 specific ledgers) not the mechanism (any
> continuously-overwritten file under automation/state/ tracked-but-rarely-committed).

> **A broader scripted audit found this is much bigger than the queue item's 8 named files:**
> ~279 tracked JSON/JSONL files under automation/state/ are ALSO last-committed 2026-07-14 with
> today's mtimes. Scoped this fire to the 8 CONFIRMED-reproduced overwritten-in-place files
> (circuit-breaker.json x6, today-bias.json x2) -- most of the other 271 are dated one-time
> snapshots or append-only historical logs (lower risk, don't regress in place) and were not
> individually triaged; filed `STATE-FILE-REVERSION-AUDIT-FOLLOWUP` (MED) in queue.md for a
> future bounded fire rather than risk a same-fire 279-file migration.

> **Fix:** exact pattern as 41889a0 -- gitignored + `git rm --cached` the 8 files (content stays
> on disk unchanged, readers are path-based and don't care about git tracking; verified both
> files still load via `json.load` post-untrack). Extended the existing guard
> (`backtest/tests/test_ledger_gitignore_guard.py`) with a `STATE_SNAPSHOTS` list + 2 new tests.
> RED-proofed: `git stash push --keep-index -- .gitignore` then re-ran the new tests ->
> `test_state_snapshots_are_gitignored` FAILED with the exact expected assertion
> (`automation/state/circuit-breaker.json is NOT gitignored`), `git stash pop` restored cleanly,
> re-verified 4/4 green. Curated pre-commit safety gate (31 tests + 5 suites) PASS at commit
> time. **Noted but NOT touched (lane discipline):** 3 pre-existing stashes were already sitting
> in the repo from other work (`git stash list` showed 3 unrelated WIP entries before my own
> push/pop round-tripped cleanly around them) -- flagging as an observation, not mine to clear.

> **REVOKE window open (rail 4 -- engine-benefit infra, not a trading-path edit).** Change:
> `.gitignore` + `git rm --cached` on 8 state files + guard test extension. Zero
> `params.json`/`heartbeat_core.py`/`filters.py`/placement/exit code touched -- this is
> infra/ops (state-file git tracking), ships per OP-22/OP-26 without J ratification. **Revert:**
> `git revert 25e31e2` (5 files: `.gitignore`, `backtest/tests/test_ledger_gitignore_guard.py`,
> + the 6 circuit-breaker.json/2 today-bias.json path re-adds are harmless either way since
> on-disk content is unaffected by tracking status). **Commit:** `25e31e2`.

> **Learn-loop:** filed `strategy/candidates/_lesson-inbox/state-file-reversion-git-ops-on-live-state-2026-07-20.md`
> flagging this as the SECOND occurrence of the SAME mechanism (07-14 ledgers, 07-20 state
> snapshots) -- OP-25 re-violation class, recommending lesson-author fold both under one L#
> rather than filing separately. The interim rule ("no git stash/checkout/clean touching
> automation/state by any session/fire") remains PROSE-ONLY -- not yet code-enforced; flagged
> in both the lesson item and the queue follow-up as the next graduation candidate (a
> git-diff-after-stash allowlist check) if this recurs a THIRD time.

> **Cost: ~$3.4** (STAGE 0/1 reads incl. engine-health/STATUS/queue/self-audit/fill-funnel,
> task-scorer, queue.md targeted reads (2129-line file, offset-read not full-read), a python
> audit script identifying the 279-file broader scope, git tracking/mtime forensics, the fix
> itself (gitignore + rm --cached + guard test extension), RED-proof round-trip, 1 curated
> safety gate run, 1 commit, lesson-inbox write, queue.md + STATUS.md writeups). **Files:**
> `.gitignore`, `backtest/tests/test_ledger_gitignore_guard.py`,
> `automation/overnight/queue.md`, `strategy/candidates/_lesson-inbox/state-file-reversion-git-ops-on-live-state-2026-07-20.md`.

---

## [2026-07-20 19:12-19:25 ET] OK -- conductor (AFTERHOURS): SHADOWEVAL-WEEKLY-TRIGGER-VS-DAILY-DOCS -- investigated a LOW doc-mismatch item, found + fixed a real 4-week silent C7 failure instead, committed

> **STAGE 0/1:** engine-health GREEN, market closed since 15:55. Fill-funnel priority-1 check
> GREEN (406/386 ticks safe/bold, 3 fills, both closed -- no funnel break). All HIGH queue
> items already CLOSED tonight by prior fires; self-audit gaps fully actioned through 07-18.
> `task_scorer.py --top` re-flagged J-decision-gated `MORNING-BULL-QUALITY-GATE-RECONSIDER`
> (correctly re-skipped, confirmed its residual question is still J-gated, not auto-shippable).
> Picked the remaining LOW queue item `SHADOWEVAL-WEEKLY-TRIGGER-VS-DAILY-DOCS` (closes a loop
> over creating an artifact; `TV-MCP-GETCHARTAPI-FIX-VERIFY` was next but this session has no
> TradingView MCP tools wired -- left pending for an interactive/Pilot session with TV MCP).

> **The original premise was a non-issue** (live-checked `Get-ScheduledTask` trigger:
> `WeeksInterval=1` + `DaysOfWeek=62` = all 5 weekdays = functionally "daily," no mismatch) --
> **but investigating it surfaced a real, much bigger bug the doc-mismatch hunt wasn't even
> aimed at:** `Gamma_ShadowEval` has fired every weekday since 2026-06-29 (real per-day logs
> exist) with Task Scheduler reporting `LastTaskResult=0`, yet **no scorecard has been produced
> since 2026-06-24** -- 4 weeks of `analysis/shadow-model/*-scorecard.md` silence, masked by the
> wscript fire-and-forget exit-code masking (same class as the `Gamma_EodFlattenCore` founding
> incident). **Root cause:** the live engine migrated from two per-account ledgers
> (`decisions.jsonl`/`aggressive/decisions.jsonl`, frozen 2026-06-25) to one consolidated
> both-accounts ledger (`core-decisions.jsonl`, materially different schema) around
> 2026-06-25 -- `shadow_model_eval.py`'s `SAFE_LEDGER`/`BOLD_LEDGER` never followed the
> migration, so every day since printed "No ticks found -- skipping" and exited 1.

> **Fixed:** `_normalize_core_row()` + a `CORE_LEDGER` fallback in `load_ticks_for_date()` --
> maps the new schema's field names to the legacy shape (`ribbon`->`ribbon_stack`,
> `htf_15m`->`htf_15m_stack`, `setup`->`setup_name`, `triggers[0]`->`trigger`, `verdict`->
> `action`, `exec.entry_px/tp/stop`->`entry_px/tp1_px/stop_px`), consulted only when the legacy
> ledger has nothing for the date (pre-2026-06-25 grading stays byte-identical). Disclosed scope
> limit: `core-decisions.jsonl` logs zero `EXIT_*` verdicts (owned by `exit_manager.py`), so
> `HOLD_RUNNER`/`EXIT_*` DT grading stays unavailable -- `ENTER_BULL`/`ENTER_BEAR`/`HOLD`/
> `SKIP_*` (the actual DT-agreement decision-bearing population) is fully restored.

> **Verified this fire:** dry-run tick counts (406 safe / 386 bold for 2026-07-20) exact-match
> `fill_funnel.py`'s independent count for the same day. New guard
> `backtest/tests/test_shadow_model_eval_core_ledger.py` (11/11), RED-proofed via `git stash`
> on `shadow_model_eval.py` alone (all 11 failed with `AttributeError: no attribute
> 'CORE_LEDGER'`, `stash pop` restored + re-verified 11/11 green). Curated safety gate
> (31+5-suite) PASS at commit time. Kicked off the REAL production eval
> (`shadow_model_eval.py --date 2026-07-20 --account both`, the exact nightly command) live in
> the background this fire -- confirmed streaming real per-tick Nemotron agreement grades
> (e.g. `t 0 09:30 HOLD -> HOLD_DEV OK (10111ms)`), not just a dry-run. ~792 ticks x 2.5s
> inter-call sleep + real LLM latency means this legitimately runs ~2h; it will keep running
> past this fire as an independent process ($0, free tier) -- check
> `analysis/shadow-model/2026-07-20-scorecard.md` directly for the finished artifact rather
> than re-running it.

> **Rail-4 N/A (not a trading-path file):** `shadow_model_eval.py` is read-only/propose-only
> by its own docstring ("NEVER imports or calls any Alpaca tool or order function... Read-only
> on production state") -- ships as engine-benefit per OP-22/OP-26, no J ratification needed.
> Zero `params.json`/`heartbeat_core.py`/`filters.py`/placement/exit code touched. **Revert:**
> `git revert 3adada9` (2 files: `setup/scripts/shadow_model_eval.py`,
> `backtest/tests/test_shadow_model_eval_core_ledger.py`). **Commit:** `3adada9`.

> **Learn-loop:** same root-cause class as the queue's own recurring C7/C14 theme (a producer
> migrates its ledger shape, a consumer silently keeps reading the old file/schema) --
> the guard test's live-ledger regression pin (`test_live_core_ledger_produces_ticks_for_a_real_recent_date`)
> IS the graduation: it will RED the moment `core-decisions.jsonl`'s schema changes again
> without a matching update here, so no separate lesson-inbox item was filed on top of it.

> **Cost: ~$4.4** (STAGE 0/1 reads incl. engine-health/STATUS/queue/self-audit/fill-funnel,
> task-scorer + queue triage across ~10 candidate items, schema investigation (3 python probes
> of core-decisions.jsonl), the fix itself (~115-line diff), 1 new 11-test guard file + RED-proof
> round-trip, 1 curated safety gate run, 1 real dry-run + 1 real background production fire,
> queue.md + STATUS.md writeups, 1 commit). **Files:** `setup/scripts/shadow_model_eval.py`,
> `backtest/tests/test_shadow_model_eval_core_ledger.py`, `automation/overnight/queue.md`.

---

## [2026-07-20 18:19-18:58 ET] OK -- conductor (AFTERHOURS): DECISION-ROW-SPY-STALENESS -- finished + shipped a fix an earlier fire left uncommitted, REVOKE-eligible, guard-tested, committed

> **STAGE 0/1:** engine-health GREEN, market closed since 15:55. self-check DEGRADED but
> both flags non-critical (cash-settlement sanity cap, trendline-draw visibility gap only).
> Top of `queue.md` Active backlog: `DECISION-ROW-SPY-STALENESS` (HIGH, filed ~18:30 ET same
> evening, "investigate before tuning ANYTHING else") -- picked over `task_scorer.py --top`'s
> `MORNING-BULL-QUALITY-GATE-RECONSIDER` per the queue item's own explicit priority framing
> + priority-1 FUNCTION FIRST (sight-integrity feeding trigger/scoring is exactly that class).

> **Investigating found the fix already ~90% built and fully wired in `heartbeat_core.py`
> (`_fetch_live_spy_quote` + `_sight_staleness_check`, both call sites, `SKIP_STALE_SIGHT`
> verdict) plus a new 23-test guard file and a quantification report -- all UNCOMMITTED,
> from an earlier fire this session (16:08-16:17 ET file timestamps). This fire's job
> became VERIFY + FINISH + SHIP, not re-derive: read the whole diff, confirmed the $1.00
> threshold is evidence-derived (not hand-picked -- n=3860 rows, real fills topped out at
> $0.63 outside the pathological cluster which hit $1.12-1.38), confirmed both fail-open
> directions are correct (no live quote -> never blocks; NEVER-BLIND doctrine), ran
> `test_sight_staleness_guard.py` (23/23), ran the two existing test files it modified
> (53/53), then the full heartbeat_core-adjacent suite (136/136, zero regressions).
> Committed `c593508` (pre-commit safety gate PASS). Closed the queue item with full
> evidence; filed one small non-blocking follow-up (`GAP-REASON-SESSION-OPEN-FALLBACK`,
> LOW -- a separate, confirmed log-only fallback-value seam at the 09:34 session open,
> does not touch trigger/scoring).**

> **REVOKE window open.** Change: entry-time freshness cross-check against Alpaca
> `/trades/latest` (not another bar-close) fires ONLY at the moment an ENTER is about to be
> attempted; diverges >$1.00 from the trigger bar's close -> `SKIP_STALE_SIGHT`, no order
> placed. PAPER accounts only (Safe + Bold core, and the fleet arms via the same core
> ledger). Revert: `git revert c593508`. Files: `setup/scripts/heartbeat_core.py`,
> `backtest/tests/test_sight_staleness_guard.py` (new), `backtest/tests/
> test_gate_provenance_ordering_2026_07_10.py`, `backtest/tests/test_money_path_2026_07_01.py`,
> `analysis/recommendations/decision-row-spy-staleness-2026-07-20.json` (new),
> `backtest/tools/fetch_spy_1min_sight_staleness.py` (new). **Commit:** `c593508`.

---

## [2026-07-20 17:42-17:58 ET] OK -- conductor (AFTERHOURS): self-audit gap batch (17:31:45, 9 items) investigated, 0 real gaps, queue hygiene fixed

> **STAGE 0/1:** engine-health GREEN (13/13), market closed. Self-audit gaps
> (`analysis/self-audit/new-gaps-flagged.md`) had a fresh un-actioned batch (2026-07-20T17:31:45,
> 9 items) filed minutes before this fire started -- priority-3, outranks queue.md HIGH items,
> so picked it over `task_scorer.py --top`'s `MORNING-BULL-QUALITY-GATE-RECONSIDER` (J-decision-
> gated, correctly skipped again per its own recurring-flag note).

> **Investigated all 9 gap claims individually (grep + live pytest, not vibes) -- found ZERO
> real actionable gaps.** This is a new failure MODE for the self-audit organ, distinct from the
> text-pattern scaffold noise already fixed 06-29/07-19: the swarm consult's perspectives
> described code content that was already FALSE by the time the consult ran, because 4 sibling
> fires landed structure-stop studies + fixes in rapid succession the SAME evening (17:00-18:05
> ET) -- the swarm caught mid-flight state, not the settled end state. Concretely: (1) margin
> mismatch = already tracked+J-pinged elsewhere; (2) resolve_zone_boundary "missing fallback" =
> FALSE, the function already returns None safely on every edge case (verified reading
> structure_stop_reference_level_ab.py:113-130) and is moot besides (REF-ZONE was NO-SHIP); (3)
> exit-diversity overlay "not merged" = FALSE, already merged + guarded
> (test_exit_patch_overlay.py, live-ran 13/13 PASS this fire); (4) margin/PDT multi-leg =
> unfounded, fleet_executor.py already force-overrides pdt_gate_mode for all fleet arms; (5)
> "incomplete" structure-stop edge-case coverage = FALSE, the exact 4 cases named
> (no-trigger/max-distance/invalid-side/no-level-set) are already individually tested in
> test_structure_stop_reference_level_ab.py; (6) missing audit trail for reference-level
> decisions = moot, both candidates NO-SHIP tonight, nothing wires to production; (7) stale
> queue state "blocking work" = partly real as a hygiene nit only (task_scorer.py already
> correctly excludes both closed items from ranking via their `status:CLOSED_*` field -- live-
> verified) -- FIXED (2 checkbox flips, queue.md); (8) over-fitting to single-trade artifacts =
> not new, this IS C24/L140, already the explicit verdict driver in tonight's own structure-stop
> DONE notes; (9) pure-function-wrapper latency "in the hot path" = FALSE, the named functions
> live in an analysis-only `backtest/tools/` module never imported by `heartbeat_core.py` or any
> live tick path.

> **Root cause + standing mitigation (no new code guard -- documented in the DONE marker
> instead):** there's no cheap way to auto-verify "was the LLM's prose claim about code content
> true" generically; that verification IS the grep-then-decide step this fire just performed.
> The existing OP-25/C7 discipline (read a self-audit gap, VERIFY against live code/tests before
> actioning, only then fix-or-dismiss) already covers this class -- this fire is a clean
> instance of that discipline working as designed, not a new gap in the gap-finder itself.

> **Verified this fire:** `python -m pytest automation/state/fleet/test_exit_patch_overlay.py -q`
> -> 13 passed. `grep` confirmed the 4 named edge-case tests exist verbatim in
> `test_structure_stop_reference_level_ab.py`. `python setup/scripts/task_scorer.py --top` ->
> `MORNING-BULL-QUALITY-GATE-RECONSIDER` (confirms closed items already correctly excluded from
> ranking before my checkbox fix -- the fix is pure hygiene, not a ranking-correctness fix).

> **Rail-4 N/A (no trading-path change):** `analysis/self-audit/new-gaps-flagged.md` (DONE
> marker) + `automation/overnight/queue.md` (2 checkbox flips, `[ ]`->`[x]` on already-
> `status:CLOSED_*` items) + this STATUS.md entry. Zero `params.json`/`heartbeat_core.py`/
> `filters.py`/placement/exit code touched. **Revert:** `git revert <commit>` if committed (2
> files, purely additive/hygiene, nothing downstream depends on it). **Not yet committed** --
> this evening has a large uncommitted-state backlog across many sibling fires (structure-stop
> studies, premarket-touch-credit study, LEVER-1 trend-alignment verdict, plus routine state-
> journal drift); did not force a bulk commit outside this fire's own scope, per rail 3 (one
> bounded task per fire, don't clobber sibling in-flight work in a shared file).

> **Learn-loop:** no new lesson-inbox item -- this fire's method (verify each self-audit gap
> claim against live grep/pytest before treating it as real, rather than actioning prose at face
> value) is the SAME discipline the 06-29 and 07-19 self-audit fixes already established for the
> text-pattern-noise failure mode; this fire demonstrates it generalizes to the stale-context
> failure mode too, without needing new code.

> **Cost: ~$2.4** (STAGE 0/1 reads incl. engine-health/STATUS/queue/self-audit-gaps triage, 9-gap
> individual grep+pytest verification pass, 2 queue.md checkbox hygiene edits, 1 self-audit DONE
> marker, this STATUS entry). **Files:** `analysis/self-audit/new-gaps-flagged.md`,
> `automation/overnight/queue.md`.

> **STAGE 1 priority-1 (fill-funnel, checked before the self-audit pick):**
> `python setup/scripts/fill_funnel.py` -> **GREEN**, TOTAL 1162 ticks -> 39 sig -> 11 ENTER ->
> 1 attempt -> 1 accept -> 3 fills -> 3 exits. core:safe fully closed (10 ENTER dedup'd to 1
> attempt/accept, 3-lot fill+exit). core:bold 18 ENTER, 0 attempts (gated upstream, not a funnel
> break -- `self_check.py` corroborates: only DEGRADED flags today are SETTLEMENT-BLOCKED[safe]
> 5/5 same-day-entry cap reached, and a non-load-bearing TRENDLINE-DRAW visibility miss). No
> funnel break outranked the self-audit-gaps pick.

---

## [2026-07-20 17:15-18:05 ET] KILL (analysis-only) -- conductor (AFTERHOURS): PREMARKET-TOUCH-CREDIT-STUDY pre-reg run, closed

> **STAGE 0/1:** engine-health GREEN (13/13), market closed. `task_scorer.py --top` re-flagged
> J-DECISION-GATED `MORNING-BULL-QUALITY-GATE-RECONSIDER` (correctly skipped, Nth recurrence).
> Self-audit gaps (`analysis/self-audit/new-gaps-flagged.md`) fully actioned through 2026-07-19.
> Both HIGH items filed today during RTH (`STRUCTURE-STOP-ZONE-BAND`, `EXTRA-SIGNAL-CHURN-
> COOLDOWN`) were already CLOSED by prior fires tonight before this fire started. Picked the
> remaining open HIGH item: `PREMARKET-TOUCH-CREDIT-STUDY` (J's own 09:36 ET premarket question,
> pre-reg study, explicitly "NOT a same-day wire").

> **Built + ran the frozen pre-reg.** Froze `analysis/recommendations/premarket-touch-credit-
> preregistration.json` before any replay. Reused `structure_stop_study.py`'s replay engine
> (SS-B, trigger-exact, buffer=0.00 -- confirmed literal live behavior by tonight's 2 prior
> structure-stop studies), `tw8_level_context.py`'s frozen per-day level set, and
> `lib.filters.detect_level_rejection`/`detect_level_reclaim` (the exact production bar-test,
> direction-matched) for premarket touch detection -- zero new hand-picked band parameter.
> Fresh-slice population: 41 signals (canonical 2025-2026 signal cache filtered to the Alpaca-
> SIP-verified premarket window 2026-05-19..2026-07-17, per DATA-PROVENANCE.md, + the existing
> 18-signal FRESH_SIGNAL_SET, deduplicated); 27 eligible (recoverable trigger_level + cached
> option bars, $0 -- no network calls). **Result: touched levels (n=15) SS-B expectancy
> -$15.88/tr vs untouched (n=12) -$302.50/tr -- delta +$286.62 directionally consistent with
> J's own read, but random-label permutation p=0.21 and shuffled-level permutation p=0.208
> (neither BH-FDR-survives at alpha=0.05). Verdict: KILL** -- the pre-reg's own disclosed-in-
> advance expected outcome for n~27. Layer (b) real-fills anchor deliberately DEFERRED (pre-
> reg scope_note: not worth ~$4 of live OPRA network calls to confirm a KILL layer (a) alone
> already resolves).

> **Verified this fire:** new guard `backtest/tests/test_premarket_touch_credit_study.py`
> (26/26 -- BH-FDR vs a textbook example, direction-matched touch detection incl. no-cross-day
> and no-RTH-bar leakage, segmentation math, full verdict-ladder branch coverage, live pre-reg/
> output sanity), RED-proofed via the file-move technique (untracked new module -- moved out,
> confirmed `ModuleNotFoundError` on all 26, moved back, re-verified 26/26 green). Broader
> sweep (`test_structure_stop_study` + `test_structure_stop_zone_band_ab` +
> `test_structure_stop_reference_level_ab` + this file) -> **72/72 PASS, 0 regressions**.
> Curated safety gate (31+5-suite) PASS.

> **Rail-4 N/A (no trading-path change):** ANALYSIS ONLY -- `analysis/recommendations/
> premarket-touch-credit-preregistration.json`, `analysis/recommendations/premarket-touch-
> credit-2026-07-20.json`, `backtest/tools/premarket_touch_credit_study.py`,
> `backtest/tests/test_premarket_touch_credit_study.py`, `automation/overnight/queue.md`. Zero
> `heartbeat_core.py`/`level_states`/`params.json`/placement/exit code touched; no wire
> attempted -- KILL means there is nothing to wire, per the item's own scope. **Revert:**
> `git revert <this commit>` (5 files) -- purely additive, nothing downstream depends on it.

> **Learn-loop:** no new lesson-inbox item -- this fire's method (reuse an already-built
> sibling study's replay engine + level-context machinery for a new segmentation question,
> rather than re-deriving trigger-level recovery / real-fill replay from scratch) is a direct
> instance of the already-proven "compound, don't accumulate" discipline this session's other
> structure-stop studies established tonight; no new foot-gun surfaced.

> **Cost: ~$4.6** (STAGE 0/1 reads + task selection incl. confirming both RTH-filed HIGH items
> already closed, machinery survey across `levels.py`/`filters.py`/`tw8_level_context.py`/
> `structure_stop_study.py`/`structure_stop_reference_level_ab.py`/`probe_stats.py`/
> `_signal_cache.py`, 1 pre-reg write, 1 ~330-line study tool, 1 local run (0 network calls),
> 1 new 26-test guard file + RED-proof round-trip, 1 broader 72-test regression sweep, 1
> curated safety-gate run, 1 queue.md closure, 1 STATUS.md entry, 1 commit -- no LLM in the
> hot path, no orders, PAPER-N/A (analysis-only)). **Files:** `analysis/recommendations/
> premarket-touch-credit-preregistration.json`, `analysis/recommendations/premarket-touch-
> credit-2026-07-20.json`, `backtest/tools/premarket_touch_credit_study.py`,
> `backtest/tests/test_premarket_touch_credit_study.py`, `automation/overnight/queue.md`.

---

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

## [2026-07-20 ~16:53-18:40 ET] LOOP CLOSED -- interactive (Fable + 5 Sonnet builders): J's "map winning trades / fine-tune / get profitable" loop -- 2 shipped, 3 honest kills/defers, 1 new HIGH lead

> **J directive (verbal, ~16:45 ET):** step back, logic not code, map winning trades from real data, loop until fine-tuned. Ran 3 iterations. **Full detail: analysis/winning-trade-map/SYNTHESIS-2026-07-20.md** (committed with the 27-episode broker-truth map).
>
> **SHIPPED (commits 508f516, 8d4ec39 + prior-session fd91712 verified):**
> - Per-arm EXIT-DIVERSITY overlay (J's arms vision): exit_patch merged over registry exit shape; matrix live for tomorrow -- FLEET-TIGHT-S=RIBBON, FLEET-TIGHT-R=control, FLEET-LOOSE-R=ZONE-RIDE (wider trail); eager+per-merge unknown-key validation incl. fleet_live.py load point (proven both ways); arm table shows exit profile per fill. 272/272 + 46/46 fresh.
> - Extra-signal re-entry cooldown (prior session's fd91712, independently verified 10/10 + 136/136): the 3-entries-in-5-min churn class is dead.
> - Winning-trade map: 27 real-fill episodes 07-13..20, reconciled to the dollar vs both day anchors (NOTE: 2026-07-20 true EOD = -$141; the -$111 was an intraday snapshot before a 5th trade, bollinger_squeeze 14:49, -$30).
>
> **HONEST KILLS / NO-SHIPS (each with frozen pre-reg, artifacts committed):**
> - STRUCTURE-STOP-REFERENCE-LEVEL: NO-SHIP -- REF-ZONE -$63.73/tr vs -$47.34 control; today's +$130 zone counterfactual was the classic single-anchor mirage. Core stop unchanged; risky-3's ZONE-RIDE arm is the live falsification rail.
> - LEVER 1 trend-alignment sizing: KILL stands (twice-confirmed, look-ahead-fixed): rho NEGATIVE (~-0.15) in both cohorts -- fully-aligned signals are the WORST bucket. "Size up with the trend" is measurably backwards for this engine.
> - LEVER 2 premium-stop -> chart-stop swap: NET WORSE on the 11-loser cohort (-$509 actual vs -$601 counterfactual); my "upper bound" premise was wrong (catastrophe cap wider than -8% brackets) -- agent corrected it against real exit_manager code. DEFER-INSUFFICIENT-DATA stands.
>
> **CORRECTION + NEW HIGH LEAD:** the morning "stops read spread noise / SPY unchanged" claim was a STALE LOGGED-CONTEXT artifact -- real tape sold off $1.48 during those holds. Filed DECISION-ROW-SPY-STALENESS (HIGH): did any ENTER key off a stale spot read? (09:51 calls-into-a-selloff = the stale-sight signature.) This is the next session's first item.
>
> **Loop exit condition met:** map synthesized, all 3 levers adjudicated, everything verified-fresh and committed (safety gate green x5). Remaining items need organic n or market hours; conductor owns the overnight cadence.

---


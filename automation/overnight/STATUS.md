## [2026-07-21 ~22:12-22:38 ET] OK -- conductor (AFTERHOURS): closed stale T-VWAPCONT-AB-VALIDATE queue item (already shipped + reconfirmed), commit `7f2ee9c`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). `fill_funnel.py` GREEN
> (core:safe 2 fills/2 exits today, core:bold 1 ENTER->0-attempt correctly excluded as SKIP_LATE_ENTRY).
> `self-check-last.json` DEGRADED on the same pre-existing non-load-bearing TRENDLINE-DRAW visibility
> flag (unchanged). Self-audit gaps: the 2026-07-21T17:31:28 batch already TRIAGED, nothing new.
> `task_scorer.py --top` again surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (J-decision-gated,
> correctly skipped). Author inboxes: lesson-inbox 3 items / chef-inbox 14 (both lower priority than
> a ready queue item). Searched `queue.md` for genuinely open (`status:open`) items across the whole
> ~2,500-line file (grep, not a full read -- file is 524KB) and found only 2: `T-AUDIT-TAIL`
> (already deprioritized by a prior fire, left as-is) and `T-VWAPCONT-AB-VALIDATE` (filed 2026-07-07,
> read as "running... if CLEARS ship via guard+revert+REVOKE" -- looked genuinely open).

> **What I found:** the A/B validation this item was waiting on had ALREADY completed and shipped
> the same week it was filed -- `vwapcont-exit-ab-ship-gate.json` (2026-07-07) verdict SHIP, all 5
> OP-22 gates PASS (parity/OOS-beats-current $75.47 vs $66.83, WF=1.62, 6/6 quarters stable, anchor
> edge_capture 82.04 vs 44.52, drop-top3 +$45.86). The queue entry's own "status:open" was simply
> never updated after the ship -- another instance of tonight's recurring T-AUDIT-cluster class
> (verified-shipped work sitting open, competing for future fires' attention against real unstarted
> work).

> **Verified this fire (OP-33), not just trusted the old scorecard:** `automation/state/params.json`
> live-read `j_vwap_cont_premium_stop_pct=-0.06` / `j_vwap_cont_tp1_pct=0.4` (doc-stamped
> `_j_vwap_cont_exit_updated_2026_07_07`); `automation/state/fleet/strategies.py:122`
> VWAP_CONTINUATION.exit carries the identical shape (both lanes synced, no two-lane drift);
> `git status --short` on both files clean (zero uncommitted drift), `git log` confirms the shipping
> commits already landed on HEAD. `pytest backtest/tests/test_vwapcont_exit_ab_ship_gate.py -q` ->
> **6/6 PASS**, fresh run against the actual working tree. **Bonus finding, not assumed:** the
> independent 2026-07-09 `vwapcont-entry-exit-matrix.json` (STOP-A ground rule 11, a pre-registered
> 24-cell grid replayed through the LIVE `exit_manager.plan_exit_actions` decision core, not just
> `simulate_trade_real`) tried to unseat this exact cell and failed -- its own `control_id:
> "P1T1F1L1"` IS the shipped -0.06/0.40 shape (`live_cell_as_of_freeze` matches byte-for-byte),
> verdict **CONTROL-STANDS**: 0/23 wider/looser challenger cells beat it on all 4 pre-registered
> conditions. This item's own stated CAVEATS ("IS-only, needs OOS confirm") are answered twice over
> -- once by the ship-gate's OOS split, once by an independent later study that tried to beat it and
> couldn't.

> **Trading-path scope:** zero trading-path files touched by THIS fire -- the params/strategies.py
> changes were already committed on 2026-07-07; this fire edited only `automation/overnight/
> queue.md` (doc-close, not code). No new guard/revert/REVOKE needed (nothing shipped that could
> regress). Curated safety gate (31+5) PASS pre-commit. **Revert:** `git revert 7f2ee9c` (1 file,
> fully additive annotation, no functional change).

> **Cost: ~$1.9** (STAGE 0/1 reads, fill_funnel + self-check + task_scorer + self-audit-gap +
> inbox survey, a targeted grep across the full 524KB queue.md for `status:open` rather than a full
> read, deep-dive into 3 scorecard JSONs + the live params/strategies.py + git log to independently
> re-verify the ship (not just trust the old note), pytest run, commit + this STATUS/queue update).

> **STAGE 0/1:** engine-health GREEN (13/13, market closed). `fill_funnel.py` GREEN (safe 2
> fills/2 exits, bold 0-attempt informational). `self-check-last.json` DEGRADED on the
> pre-existing non-load-bearing TRENDLINE-DRAW visibility flag only (unchanged from earlier
> fires). `task_scorer.py --top` again surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER`
> (J-decision-gated, correctly skipped). Self-audit gaps: nothing new since the last triaged
> batch. Author inboxes: lesson-inbox has 3 unactioned items, chef-inbox 14 — lower priority
> than a ready queue item this fire. Surveyed `queue.md` HIGH items: `DOJO-BUILD-HANDOFF`
> confirmed NOT pickable again (this session's tool set has zero TradingView MCP tools, only
> Alpaca account/position/clock + file/bash — matches the prior fire's own note, not
> re-derived blind). Found `T-AUDIT-01..05` (an 2026-07-07 audit-fix cluster) sitting
> unclosed despite their own fix comments dated 2026-07-07/08.

> **What shipped:** re-verified all 4 non-policy items (T-AUDIT-02/03/04/05) against LIVE
> code before closing, not just trusting the old note: (a) expired-level filter —
> `heartbeat_core.py:376` `FIX2 (2026-07-07)` skips any level whose `expires_at` predates
> today, fail-open on missing/unparseable; (b) fill reconciliation — `heartbeat_core.py:1170`
> `_reconcile_fill` `FIX3 (2026-07-07)` polls the placed order to a terminal state
> (bounded retries, 3s hard cap) instead of leaving it `pending_new`/`filled_qty=0` forever;
> (c) `fill_funnel.py` false-RED — `NOT_FLAT`/`SKIP_*`/`RISK_DENY_*` explicitly excluded from
> `attempted` (2 rounds, 07-07 + 07-08); live run tonight confirms GREEN; (d) `time_stop_et` —
> `heartbeat_core.py:987` passes `params.get("time_stop_et")` through to
> `exit_actuator.manage_tick` -> `exit_manager.parse_time_stop_et`, confirmed NOT hardcoded
> 15:50 (`params.json:39` carries `"15:40"` live). **T-AUDIT-05's own "EVIDENCE WAS TRUNCATED
> -- re-verify grep before fixing" instruction was followed literally** — the re-verify
> proved the fix already shipped, not that it needed (re-)building.

> **Verified this fire (OP-33):** `pytest -k time_stop -q` -> 26 passed;
> `pytest -k audit_fix -q` -> 36 passed (both fresh runs against the actual working tree, not
> assumed from the old fix comments). No code changed — this is a pure queue-hygiene closure
> (OP-22 compound-don't-accumulate): the cluster was fixed weeks ago and never pruned, so
> every subsequent conductor fire was re-reading (and now correctly re-skipping) already-dead
> work. `T-AUDIT-01` (a genuine manual-vs-engine coexistence POLICY fork) correctly left
> `awaiting-j-ratification` — not something a conductor fire decides. `T-AUDIT-TAIL`
> (recover a truncated old synthesis run) left open but downgraded — its own worry (more
> undelivered items in that cluster) is moot now that 02-05 are confirmed closed.

> **Trading-path scope:** zero trading-path files touched — this fire edited only
> `automation/overnight/queue.md` (documentation/state, not code). No guard/revert/REVOKE
> needed (nothing shipped that could regress). **Revert:** `git revert f17f054` (1 file,
> fully additive annotation, no functional change).

> **Cost: ~$1.7** (STAGE 0/1 reads, grepping 4 code paths to re-verify each fix live, 2 pytest
> runs, the queue.md edit, commit, this STATUS/queue update).

---


> **STAGE 0/1:** engine-health GREEN (13/13, market closed). `task_scorer.py --top` again
> surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still J-decision-gated, correctly skipped).
> `self-check-last.json` read **verdict=BROKEN**: "DRESS-REHEARSAL RED: broker-boundary
> rehearsal at 2026-07-21T20:45:02 FAILED ... Tomorrow's open is NOT proven." Per STAGE-1
> priority-2 (Engine RED / STATUS BROKEN outranks every inbox/queue item), this was the fire's
> task -- a self-check BROKEN on the literal "are we good for tomorrow" instrument is exactly
> the class this conductor exists to catch before it becomes a missed morning open.

> **Root cause (one sentence):** `check1_options_safe`'s end-state check queried Alpaca's
> `GET /v2/orders?status=open` listing immediately after the single-order `GET` had already
> confirmed the probe order canceled -- that list endpoint is backed by a different index than
> the single-order lookup and can lag it ~1-2s (eventual consistency), so the just-canceled
> order still showed up as "open" for one query. Evidence: `dress-rehearsal.json` showed
> `check1_options_bold` GREEN on the byte-identical code path moments later -- same
> non-determinism, not a real broker-side residue (no genuine order/position leak, verified by
> re-reading the raw evidence before touching code, per debugging-discipline "read evidence
> before hypothesizing").

> **What shipped:** `setup/scripts/dress_rehearsal.py` -- end-state open-orders/positions check
> now retries up to 5x (1.5s apart, `END_STATE_RETRIES`/`END_STATE_RETRY_SLEEP`), same shape as
> the file's own pre-existing `_flatten_crypto` verify-flat retry pattern, before declaring
> NOT CLEAN. 3 new guard tests in `backtest/tests/test_dress_rehearsal.py`
> (`TestEndStateRetryTolerance`): transient staleness clears on retry: GREEN + 3 tries;
> genuine persistent residue still REDs after `END_STATE_RETRIES` tries (never silently
> softened -- the whole point of this instrument per its own docstring); the clean case costs
> only 1 try (no added latency on the common path).

> **Verified this fire (OP-33):** 31/31 pytest PASS on the actual commit + curated safety gate
> (5-suite) PASS (`[safety-gate] PASS -- curated safety gate (5 suites) green`, quoted from the
> pre-commit hook output). **Also re-ran the LIVE rehearsal against the real Alpaca paper API**
> (not just the unit guards) -- `dress_rehearsal.py` now returns `overall=GREEN`, all 4 checks
> GREEN (was RED on `check1_options_safe`). Re-ran `self_check.py`: verdict moved
> **BROKEN -> DEGRADED** (only remaining item is the pre-existing, self-described
> non-load-bearing TRENDLINE-DRAW visibility flag -- unrelated, not this fire's scope).
> Tomorrow's 2026-07-22 open **is now proven** by the instrument built for exactly that purpose.

> **Trading-path scope:** touches `setup/scripts/dress_rehearsal.py` (a paper-account
> pre-flight PROBE script, not the live placement/exit path itself -- `heartbeat_core.py` was
> read-only imported, never edited) + its guard + the refreshed live artifact. Ships as an
> infra/engine-benefit fix (rail 1 priority-2 CRITICAL class) with guard test + clean
> git-revert path, no J ratification needed. **Revert:** `git revert d6cc86a` (3 files:
> the retry loop, the 3 new guard tests, the artifact refresh -- fully additive/reversible).

> **Cost: ~$1.5** (STAGE 0/1 reads, root-cause read of `dress_rehearsal.py` +
> `dress-rehearsal.json` raw evidence, the fix, 3 new guard tests authored + iterated to
> green, live re-run against real Alpaca API to verify the actual fix (not just the mock),
> self_check re-run, commit + this STATUS/queue update).

---

## [2026-07-21 ~20:42-21:10 ET] OK -- conductor (AFTERHOURS): QQQ divergence/confluence first-pass -- QQQ_AGREEMENT_INFORMATIVE, commit `1e16b09`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). `fill_funnel.py`
> checked: safe/bold both GREEN (bold's 1 ENTER->0-attempt row is an excluded informational
> status per the script's own false-RED-fix classes, not a bug). Self-audit gaps: the
> 2026-07-21T17:31:28 batch already TRIAGED by an earlier fire today, nothing new. `queue.md`
> HIGH survey: all remaining HIGH items are J-decision-gated / Fable-methodology-gated /
> evidence-accrual-blocked (unchanged from earlier fires' findings). Picked chef-inbox
> priority-5: `_chef-inbox/2026-07-11-prospector-qqq_divergence_confluence.md`, explicitly
> named by the 20:12-20:53 fire as the single highest-readiness item, deferred pending "a
> future chef fire with its own budget" -- this fire was that budget.

> **What shipped:** fetched real QQQ 5m bars (69,978 bars, 2025-01-02..2026-06-18, Alpaca
> SIP, paginated, cached `analysis/backtests/cache/qqq-5m-2025-01-01_2026-06-18.csv` --
> zero new external data-feed risk). Labeled all 250 canonical `ribbon_ride` signals
> (`_signal_cache.load_or_build_signals()`, reused unmodified) with QQQ's own no-look-ahead
> 20-bar rolling high/low reclaim/failed/none at each signal's `entry_ts`. Stratified a
> clearly-disclosed spot-return proxy (direction-aligned SPY forward return over 30 min --
> NOT a $ P&L, NOT a real fill, per the standard staged-research discipline: cheap
> information test BEFORE funding the expensive real-OPRA replay). Result: reclaimed n=21
> mean +1.08 SPY pts / failed n=27 mean +0.55 / none n=202 mean +0.07 -- spread +0.96,
> verdict **QQQ_AGREEMENT_INFORMATIVE**. Honestly flagged an open confound in the write-up
> (failed ALSO beats none -- may be a trend-day/volatility proxy, not pure QQQ-specific
> confirmation) as the first thing the funded real-fills follow-up must resolve. NOT a
> wiring proposal -- explicitly not eligible for `conductor-proposals.jsonl` on its own.
> New reusable tool `backtest/tools/qqq_divergence_confluence_study.py` + guard
> `backtest/tests/test_qqq_divergence_confluence_study.py` (9/9 PASS). Candidate doc:
> `strategy/candidates/2026-07-21-205400-qqq-divergence-confluence-first-pass.md`.
> Chef-inbox item closed (renamed `.DONE`, 14->13 open), `_chef-log.jsonl` + `_LEADERBOARD.md`
> updated (Rank I, NEEDS-MORE-DATA).

> **Foot-gun hit + lesson filed (not graduated yet, first occurrence):** RED-proofing the
> new guard via `git stash -- <untracked file>` failed (git can't pathspec-stash a file
> that was never tracked), and because the follow-up commands in that Bash call weren't
> `&&`-chained, a bare `git stash pop` ran anyway and nearly popped an UNRELATED
> pre-existing stash left by another session. It aborted safely on its own (this shared
> checkout has ~2,400 files modified-but-uncommitted at any time -- conflicts blocked the
> pop) -- verified `git stash list` unchanged (3 pre-existing stashes intact) and my new
> files untouched before proceeding. Switched to rename/restore (`mv`) for the actual
> RED-proof. Filed `_lesson-inbox/2026-07-21-git-stash-in-shared-checkout-pops-wrong-stash.md`
> (candidate L236) -- the durable takeaway: **never use `git stash`/`git stash pop` in this
> repo's automation context** (same root class as C34).

> **Verified this fire (OP-33):** curated safety gate (31+5-suite) PASS on the actual
> commit (pre-commit hook output quoted: "31 passed in 1.34s ... [safety-gate] PASS").
> `git diff --cached --stat` confirmed exactly the 10 intended files before committing.
> Post-commit `git show HEAD --stat` + `git ls-tree HEAD` confirmed the rename landed
> (`.md.DONE` present, original path absent) and the new files are all tracked. Commit
> `1e16b09`.

> **Zero trading-path files touched** -- pure research/authoring work (new tool + guard +
> analysis outputs + inbox/leaderboard/lesson bookkeeping). Ships as engine-benefit per
> OP-22/OP-25/OP-26, no J ratification needed. **Revert:** `git revert 1e16b09` (10 files,
> additive except the 2 append-only ledgers and the .DONE rename -- no data loss).

> **Cost: ~$4.5** (STAGE 0/1 reads incl. fill_funnel + self-audit-gap + queue.md HIGH
> survey, deep-dive into 5 existing backtest tools to find the reusable signal-cohort +
> SPY-loader + probe_stats machinery before writing anything new, ~300-line new study
> script + ~130-line guard test authored + iterated to green, live QQQ bar fetch (69,978
> bars), the actual stratification run, candidate write-up with OP-20 disclosures,
> leaderboard/chef-log/inbox bookkeeping, the git-stash near-miss investigation +
> lesson write-up, commit + post-commit verification, this STATUS/queue update).

---

## [2026-07-21 ~20:12-20:53 ET] OK -- conductor (AFTERHOURS): drained chef-inbox backlog 31->14 open + rejected late-entry-ceiling hypothesis, commit `3422e7b`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). `task_scorer.py --top`
> again surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (confirmed still J-decision-gated via
> queue.md's own text, correctly skipped). Self-audit gaps fully triaged (nothing new since the
> 2026-07-21T17:31:28 batch, already TRIAGED by an earlier fire today). Checked `_chef-inbox/`
> (STAGE 1 priority-5, author inboxes oldest-first) and found **31** un-actioned items dating
> back to 2026-07-09 (12+ days stale) -- chef's own log (`_chef-log.jsonl`) last fired
> 2026-07-07, meaning this inbox has been silently accumulating for 2 weeks while higher-
> priority items always won the STAGE-1 pick. **No Agent-tool available this session** (tool
> list was Read/Edit/Write/Bash/Grep/Glob + Alpaca MCP only) -- acted directly as chef per its
> own guardrails (DRAFT-only, no live orders, no params/CLAUDE.md edits) rather than deferring.

> **What shipped:** (1) REAL backtest on Analyst's 07-14 `late-entry-ceiling-review` item: 71
> raw `SKIP_LATE_ENTRY` rows from live `core-decisions.jsonl` (2026-07-07..07-21, all the ledger
> retains) grouped into 19 distinct re-confirming episodes, joined to a fresh SPY 5m bar cache.
> Sweeping the ceiling to 15:15/15:30/15:40 would only have been directionally favorable
> 10%/31%/31% of the time by the 15:50 flatten -- REJECTED, converges with the prior
> `agg_block_bull_morning_afternoon` POWER_HOUR finding (n=3, WR=33%, -$45) via an independent
> method+dataset. Written up with full OP-20 disclosures at
> `strategy/candidates/2026-07-21-202600-late-entry-ceiling-reconsider.md` (leaderboard rank 47).
> (2) Rejected 10 prospector items with live evidence: `yf.Ticker('^TICK'/'^ADD'/'^TRIN')` all
> 404 (the "free via Yahoo Finance" claims were wrong -- caught a genuine swarm inconsistency,
> a sibling item labels the same NYSE-TICK data "Cost: paid"), NYSE OpenBook + FlowAlgo "free
> tier" are licensed/marketing not programmatic APIs, 4 items self-labeled "Cost: paid" outright.
> (3) Consolidated 6 duplicates into 3 canonical masters (VIX1D family -- feasibility VERIFIED
> this fire via a live `^VIX1D` probe, real daily bars; TV Volume-Profile-shelf family; FRED
> treasury-yield-curve family), each left OPEN with a concrete next-step note instead of
> re-litigating cold on a future fire. (4) Flagged `qqq_divergence_confluence` as the single
> highest-readiness remaining item (fully spec'd in `CROSS-TICKER-BRAINSTORM-2026-07-10.md`,
> zero new data-feed risk) for the next chef fire's top pick. (5) Filed a lesson-inbox item
> (`_lesson-inbox/2026-07-21-prospector-free-claim-not-verified-before-cost-tag.md`) documenting
> the free-claim-hallucination pattern -- first occurrence, not yet graduated to code, watching
> for a repeat per OP-25.

> **Verified this fire (OP-33):** curated safety gate (31+5-suite) PASS on the actual commit
> (pre-commit hook output quoted: "31 passed in 1.47s ... [safety-gate] PASS"). `git diff
> --cached --stat` confirmed exactly 26 intended files before committing (no scope creep in the
> large actively-churning shared checkout -- left an unrelated pre-existing uncommitted
> `_review-log.jsonl` change untouched, not mine to stage). Post-commit `git show HEAD --stat` +
> `git ls-tree HEAD` confirmed the renames landed correctly (12 tracked `.DONE` files present,
> originals absent) and `ls` on disk confirmed 14 open items remain (12 tracked + 2 items from
> today that were never committed in the first place, correctly left untouched). Commit `3422e7b`.

> **Zero trading-path files touched** -- pure research/author-inbox work. Ships as
> engine-benefit per OP-22/OP-25/OP-26, no J ratification needed. **Revert:** `git revert
> 3422e7b` (26 files, restores all 15 renamed-to-.DONE originals + removes the 2 new inbox
> masters' annotations + the new candidate/lesson files). **Not done this fire (named for next
> chef pick):** the actual QQQ-divergence-confluence backtest (design ready, needs a fresh QQQ
> bar fetch — real work, not a triage item); 2 items still genuinely unverified (Alpha Vantage
> intraday rate limits, Polygon.io free-tier delay, IEX Cloud current status) — left open,
> honestly un-investigated rather than guessed.

> **Cost: ~$7.5** (STAGE 0/1 reads, task_scorer, self-audit-gap re-check, reading all 31
> chef-inbox items across 5 batches, 2 live yfinance feasibility probes, a real 19-episode
> SPY-bar-joined backtest with a fresh CSV cache, writing a full OP-20-disclosed candidate +
> leaderboard row + chef-log entry + lesson-inbox item, 17 file dispositions via a scratch
> script, commit + post-commit verification, this STATUS/queue update).

---

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). `task_scorer.py --top`
> re-surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still correctly J-decision-gated). Self-audit
> gaps fully triaged (2026-07-21T17:31:28 batch already TRIAGED by an earlier fire today). Checked
> `_lesson-inbox/` (STAGE 1 priority-5, author inboxes oldest-first) and found **5** un-actioned
> items, all filed by earlier fires TODAY (2026-07-21) -- an inbox that would otherwise sit
> un-drained until a future fire happened to look, exactly the class this stage exists to prevent.

> **What shipped:** read all 5 items in full and wrote **L231-L235** in
> `markdown/doctrine/LESSONS-LEARNED.md`, each citing the specific commit/file/test that already
> fixed the acute instance: L231 (a doc's own "shipped/verified" claim isn't proof `git commit`
> ran -- folds into C35 alongside L221), L232 (a test hardcoding a "TODAY" date literal but
> relying on a REAL filesystem mtime is a time-bomb, not a passing test -- new C6/C7 angle), L233
> (a silently-reset producer idempotency state floods a downstream author inbox for weeks with
> zero crash/RED symptom -- folds into C34 alongside L214/L228), L234 (a "real fills" arm-scope
> filter goes synthetic-by-omission when the live account lineup moves on without the loader's
> scope being re-verified -- folds into C14), L235 (a shared loader documented to return a
> full-history WARMUP frame is not automatically safe to iterate as a single-day EVENT stream --
> folds into C6). Folded all 5 into the CLAUDE.md OP-25 index (C6/C7/C14/C34/C35 rows), bumped
> the "current through" pointer L230->L235. Deleted all 5 processed inbox items.

> **Verified this fire (OP-33), applying L231's own lesson before writing this line:** curated
> safety gate (31+5-suite) PASS both pre-commit (manual run) and via the pre-commit hook on the
> actual commit. `git diff --cached --stat` confirmed exactly the 7 intended files staged (2
> edits + 5 deletions) before committing -- no accidental scope creep in this large, actively-
> churning shared checkout. Post-commit, `git ls-tree HEAD` confirmed the 5 inbox paths are
> correctly ABSENT and `git show HEAD:markdown/doctrine/LESSONS-LEARNED.md` confirmed 7 `## L23x`
> headers present, `git show HEAD:CLAUDE.md` confirmed the "current through L235" pointer landed
> -- not just a green pytest run. `check-context-budget.ps1` -> YELLOW 8548/9000 (95%), inside
> budget after the index-row growth. Commit `d827cd3`.

> **Zero trading-path files touched** -- pure doctrine/lesson-index update. Ships as
> engine-benefit per OP-22/OP-25/OP-26, no J ratification needed. **Revert:** `git revert
> d827cd3` (7 files, 2 edits + 5 restored deletions, no data loss). **Not done this fire
> (deliberately, scope discipline):** none of the 5 lessons' own "owed" follow-ups (wiring
> `verify_committed` into conductor STAGE 5 for L231; a drift-ratchet guard for L234; a broader
> producer-idempotency sweep for L233) were built -- each lesson explicitly flags its follow-up as
> future work, not required to close the inbox drain itself.

> **Cost: ~$2.3** (STAGE 0/1 reads, task_scorer + self-audit-gap re-check, reading all 5 inbox
> items in full, composing 5 cite-or-defer lessons + OP-25 fold, context-budget check, safety
> gate x2, commit + post-commit `git ls-tree`/`git show` verification, this STATUS/queue update).

---

## [2026-07-21 ~19:12-19:15 ET] OK -- conductor (AFTERHOURS): closed stale-but-shipped J-INTENT-EXECUTOR queue item, no code change

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). Self-audit gaps fully
> triaged (`new-gaps-flagged.md`'s 2026-07-21T17:31:28 batch already TRIAGED by an earlier fire
> today, nothing un-actioned). `task_scorer.py --top` again surfaced
> `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still J-decision-gated, correctly skipped). Author
> inboxes checked (5 open `_lesson-inbox` items, all from earlier today's fires -- not
> re-actioned, that's `lesson-author`'s lane). Surveyed all 8 top-level HIGH queue.md items:
> `WF-GATE-STRUCTURALLY-NULL` / `WF-GATE-REDESIGN-METHODOLOGY` are Fable-judgment-gated (not a
> Sonnet call); `VETO-HTF-CONFLICT-REGRADE` is LEFT OPEN pending organic evidence accrual (n>=5
> non-HTF comparison cohort, no action available this fire beyond a re-run that wouldn't move the
> count); `BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL` still blocked on n>=20 Bold fills (0 since the
> 07-18 wire, re-checked); `J-ONLY-COMPANION-PUSH-ACTIVATION` is J-action-required (Tailscale +
> phone tap, not conductor-pickable); `STATE-FILE-REVERSION-2026-07-20` + its
> `AUDIT-FOLLOWUP` are both effectively closed (CLOSED_PARTIAL + status:done, mechanism-level fix
> shipped 07-21 01:xx). That left `J-INTENT-EXECUTOR` (filed 2026-07-15, never marked closed) as
> the one HIGH item with real, bounded, closeable work.

> **What I found:** `J-INTENT-EXECUTOR` was fully built, wired, and scheduled back on 2026-07-18
> (`setup/scripts/j_intent_executor.py`, 38.4KB) but its queue.md entry was never annotated
> CLOSED -- a "shipped but the ledger doesn't know it" loop sitting open, competing for a future
> fire's attention against real unstarted work (OP-22 compound-don't-accumulate: closing a stale
> loop outranks starting a new artifact).

> **Verified this fire (OP-33), did not just trust the file listing:** confirmed
> `Gamma_JIntentExecutor` registered in `SCHEDULED-TASKS.md` (09:25 ET weekdays);
> `automation/state/j-intents.json` is the live store, default-empty (pure no-op when idle, by
> design). Re-ran the item's OWN acceptance gate fresh: `pytest backtest/tests/
> test_j_intent_executor_replay.py -q` -> **23/23 PASS**, and inspected the fixture directly --
> `spy_5m_2026-07-15_j_intent_752p.csv` reproduces the EXACT real trade the acceptance gate names
> (entry bar closes 13:15 ET @ 751.785 < 751.94 confirm-close; chart-stop exit bar closes 13:20 ET
> @ 752.405 > 752.26 stop), byte-matching the numbers written into the gate's own prose. Annotated
> the queue.md item CLOSED with this evidence.

> **Zero code/trading-path files touched** -- this fire's only write was a queue.md doc-append
> (closing a stale ledger entry with fresh verification evidence). No guard/revert/REVOKE
> machinery needed (rail 4 doesn't apply -- no behavior changed). **Cost: ~$1.5** (STAGE 0/1
> reads, task_scorer, self-audit-gap + inbox + all-8-HIGH-item survey across ~500 queue.md lines,
> live file/schedule verification, guard re-run, fixture inspection, this STATUS/queue update,
> conductor_outcome recording). Autonomy metric this fire: net_improvement 98/20-fire-window,
> trend **improving**, zero regressions.

---

## [2026-07-21 ~18:42-18:58 ET] OK -- conductor (AFTERHOURS): zoom-aware trendline classification shipped, commit `c741d1d`

> **STAGE 0/1:** engine-health GREEN (13/13, market closed since 15:55). Self-audit gaps fully
> triaged (nothing new/un-actioned in `new-gaps-flagged.md`). `task_scorer.py --top` again
> surfaced `MORNING-BULL-QUALITY-GATE-RECONSIDER` (still J-decision-gated). Checked
> `BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL`'s n>=20 readiness first: real trades.csv shows **0**
> Bold trades since the 2026-07-18 ATM wire -- nowhere near ready, correctly deferred (not
> re-triaged further). Picked queue.md's still-open HIGH item `TRENDLINE-FIXES-2026-07-17` #3
> (ZOOM-AWARE DRAWING, filed 2026-07-17, deferred by items 1/2/4's own text: "should reconsider
> the draw cap together with same_day-tier visibility once it ships").

> **What shipped:** `trendline_engine.zoom_classify(a_unix, now_unix, window_days=2.0)` +
> `Trendline.zoom_class` ("in_window" | "anchor_offscreen", additive field, default preserves
> every existing caller/reader byte-identical) -- classifies each detected line's anchor against
> a ~2-day window ending at the line's OWN last bar (never wall-clock time, mirrors T15's
> same-day-tier no-look-ahead pattern exactly). Opt-in via `detect(include_zoom_class=True)`,
> wired live at the ONE production entry point (`main()`, same call site as T15's
> `include_same_day_tier=True`) so both `Gamma_Trendlines`'s 5-min cadence and the on-demand
> `--json` skill invocation get it for free. `write_live_state`'s JSON payload now carries
> `zoom_class` per line. `.claude/skills/trendline-draw/SKILL.md` gained a new step 3a
> documenting the label-offset behavior J's queue item asked for: draw the full ray regardless,
> but flag `anchor_offscreen` lines verbally and cross-check `chart_get_state` before trusting
> the bars-only heuristic over the actual chart.

> **Verified this fire (OP-33):** new guard `backtest/tests/test_trendline_zoom_aware.py` (13/13)
> RED-proofed via `git stash -- backtest/autoresearch/trendline_engine.py` alone -- all 13 failed
> pre-fix with the exact expected `TypeError`/`AttributeError` (missing kwarg / missing
> function), `git stash pop` restored cleanly (confirmed only my own stash entry existed;
> pre-existing unrelated stashes from earlier sessions left untouched per C34/L214/L228), and
> re-verified 13/13 green. Caught + fixed a real test-fixture bug during RED-proofing (the
> original 1-day-apart fixture put day1's anchor INSIDE the 2-day window relative to day2's
> "now", so `anchor_offscreen` never actually fired -- widened the fixture gap to 6 calendar
> days). Broader sweep `pytest backtest/tests/ -k trendline` -> **99/99 PASS, zero regressions**.
> Curated safety gate (31+5) PASS. `git ls-tree HEAD` confirmed all 4 files (engine, guard test,
> SKILL.md, queue.md doc-update) landed on HEAD, not just staged -- commit `c741d1d`.

> **Zero trading-path files touched** -- `trendline_engine.py`'s consumption remains SHADOW-only
> (`write_live_state`'s own docstring: "the engine does NOT trade off these yet"); `params.json`/
> `heartbeat_core.py`/`filters.py`/placement/exit code untouched. Ships as engine-benefit per
> OP-22/OP-26, no J ratification needed. **Revert:** `git revert c741d1d` (4 files, additive +
> one doc-append each, no data loss). **NOT done this fire, deliberately deferred (stated
> up front in the queue.md item, not silently dropped):** on-chart screenshot validation against
> the ACTUAL TradingView visible range -- this conductor fire has no live TV MCP tool binding
> (headless), so `zoom_class` is a bars-only heuristic approximation, not yet a proven fix for
> J's visual complaint. The next interactive session with a live TV chart should invoke the
> trendline-draw skill, deliberately surface a multi-day line that comes back
> `anchor_offscreen`, and confirm the on-chart result actually reads clean at J's normal intraday
> zoom before this queue item is considered fully closed (queue.md item 3 left open with this
> note, matching item 2's same "SHADOW-only, mechanism-guard-not-P&L-A/B" shipping bar).

> **Cost: ~$4.7** (STAGE 0/1 reads incl. self-audit-gap/inbox sweep, task_scorer, BOLD-ATM
> readiness check via real trades.csv, queue.md HIGH-item survey across ~350 lines, trendline_
> engine.py source survey, design + implementation, 13-test guard file + one round of fixture-bug
> fix found during RED-proofing, broader 99-test sweep, curated safety gate x2, SKILL.md doc
> update, commit + `git ls-tree HEAD` verification, this STATUS/queue update).

---

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


### DEGRADED: self-check 2026-07-21T22:09:56
- TRENDLINE-DRAW never marked today (2026-07-21) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.

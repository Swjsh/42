## Known broken

- [2026-07-31T15:30:22] GATE-EXPIRY RED :: block_elite_bull :: refused cohort would have EARNED $13.15/tr, n=97 >= floor 10 -- COSTING money :: re-check: backtest\.venv\Scripts\python.exe backtest\autoresearch\gate_expiry_check.py --gate block_elite_bull
_Standing OP-25 flag surface. Producers append ONE loud line here on a transition into a broken/RED state (never re-spam a persisting flag) -- see `setup/guard_runner_slow.py::_flag_status_md` and `backtest/autoresearch/gate_expiry_check.py::flag_status_md` for the exact pattern. STRUCTURAL NOTE (found + fixed 2026-07-31, gate-expiry-instrument build): this header used to live INSIDE individual dated `## [...]` entries, so `setup/scripts/status_retention.py`'s byte-budget rolling (which only ever preserves the file's PREAMBLE -- everything before the first `## [` entry -- forever) carried it off to the monthly archive the moment the entry containing it aged out. Every producer targeting this marker was silently no-op'ing (marker not found -> fail-open no-write) for an unknown span before this fix. Moving it into the permanent preamble makes it immune to retention rolls going forward. If this section grows large, prune resolved lines by hand (OP-22 consolidation) rather than letting status_retention.py touch it -- it never will._

---

## [2026-07-31 ~09:12-09:35 ET] OK -- conductor (AFTERHOURS): LIVE TV-CDP outage fixed pre-open + self-heal blind-spot closed, commit `c941567c`

> **STAGE 0/1:** ET 09:12 Friday (pre-open, market closed until 09:30). Budget gate
> PROCEED ($11.44/$30, 2/4 fires). `self-check-last.json` showed `BROKEN`: TV-CDP
> unreachable on :9222, ~18 min before market open. Per STAGE-1 priority-1/2
> (function-first / Engine RED), investigated + fixed first before anything else.

> **LIVE-VERIFIED (OP-33), not guessed:** `curl :9222/json/version` confirmed CDP
> genuinely down. `Gamma_TvWatchdog` log showed it had ALREADY tried to self-heal twice
> (RELAUNCH_KILL at 09:05 and 09:10 ET, `CDP dead for 3896s` -> `4196s` -- growing, not
> shrinking) -- both attempts silently failed with no distinguishing signal from a
> successful relaunch. Manual `taskkill /F /IM TradingView.exe` + relaunch fixed it live
> (`curl` now returns a valid CDP payload, `self_check.py` flipped `BROKEN` -> `DEGRADED`).

> **ROOT GAP (C7 silent-success-is-failure):** `Invoke-TvLaunchSafe` (`_shared.ps1`)
> returned only `{skipped}` -- no signal whether the relaunch it just ran actually
> restored CDP. `run-tv-watchdog.ps1`'s 3 call sites logged the identical `relaunch_kill`
> shape whether the fix worked or not, so a genuinely-failing self-heal looked the same
> in STATUS.md as a working one for 70+ minutes until an unrelated producer
> (`self_check.py`) caught it independently.

> **FIX SHIPPED:** `Test-CdpReady` poll helper + `Invoke-TvLaunchSafe` now self-verifies
> post-launch and returns `{skipped, healed}`; the 3 watchdog call sites branch into
> `*_healed` / `*_FAILED` tvActions, and a `*_FAILED` outcome writes a distinct
> append-only `### BROKEN:` STATUS.md block instead of blending into routine noise.
> **Also closed a separate small gap while touching this file:** `test_tv_launch_safe_
> 2026_07_06.py` existed on disk (dated 2026-07-06) but had NEVER been `git add`-ed
> (L242-shape) -- committed it now alongside the new assertions it needed anyway.

> **Verified (OP-33):** 7/7 tv-launch-safe tests green (incl. 2 new), 40/40 related
> infra-watchdog suite green, 59/59 curated safety gate green. Live CDP re-confirmed up
> AFTER the code change (not just before). `git show c941567c --stat --name-status`
> confirms exactly the 3 intended files (L247 discipline).

> **Open question, logged not chased further (debugging-discipline discipline):** WHY
> the 09:05/09:10 production relaunches failed while 2 manual reproductions of the
> identical code path (same Interactive-logon task principal) both succeeded minutes
> later was not fully root-caused -- ruled out AppX-query flakiness (5/5 manual reps
> clean) and window-station mismatch (principal confirmed Interactive). The shipped fix
> makes a recurrence LOUD regardless of the underlying mechanism, which is the
> higher-leverage response; chasing the exact intermittent trigger further was not a
> good use of this fire's budget. Lesson filed:
> `_lesson-inbox/tv-selfheal-silent-failure-2026-07-31.md` (also flags
> `Invoke-LevelRefreshSafe` + `state_freshness_selfheal.py` as worth auditing for the
> same verify-the-effect-not-just-the-attempt gap).

> **Scope + revert:** 2 infra scripts + 1 test file. Zero params/heartbeat_core/filters/
> placement/exit/CLAUDE.md touched. Revert: `git revert c941567c`.

---

## [2026-07-31 ~05:30-05:57 ET] OK -- conductor (AFTERHOURS): 4 un-actioned self-audit batches triaged + closed, commit `aed731f2`

> **STAGE 0/1:** ET 05:30 Friday (market closed). Budget gate PROCEED ($10.78/$30, 1/4 fires).
> `engine-health.json` clean (14 GREEN, gex_archive 1-day interior-gap YELLOW non-critical,
> no RED). `self-check-last.json` GREEN. STAGE-1 priority order: function-first (fill-funnel)
> clean, no Engine RED -- landed on priority-3, self-audit gaps: `analysis/self-audit/
> new-gaps-flagged.md` had 4 CONSECUTIVE un-triaged daily-swarm batches (2026-07-26 through
> 2026-07-29, ~32 lines), the longest un-actioned backlog since this pipeline started
> (normal cadence closes same-day or next-day).

> **Live-verified every substantive claim rather than re-deriving (OP-33):** the recurring
> "conductor firing far more than max_fires" line (named in 3 of the 4 batches) was already
> root-caused and fixed 2026-07-29 (commit `631798f0`, cross-midnight substring bug in
> `conductor_budget.py::spend_today`) -- re-confirmed live this fire (`PROCEED $10.78/$30,
> 1/4 fires`, correct for today). "Claude-native task governance requires manual
> intervention / hard-stop risk" -- read `audit_scheduled_tasks.py` live: read-only,
> fail-open, surfaces to STATUS.md only, no hard-stop code path exists. "Auto-commit of
> strategy/candidates without validation creates noise" (appeared twice) -- read
> `auto_commit_candidates.py` live: scoped to `strategy/candidates/` only, pathspec (never
> `-A`), fail-open, fires at >=10 pending changes; live `git status --porcelain
> strategy/candidates` showed only 2 pending -- working as designed, not a noise source.
> "No live-to-paper shadow mode while RED-blocked" -- already built (TRADE-TO-LEARN,
> CLAUDE.md rail-4). "Git commits abused as a runtime config toggle (DO_NOT_ARM/FROZEN)" --
> grepped every hit across `setup/scripts`+`backtest/autoresearch`: all are `FROZEN_CONFIG`
> frozen-dataclasses (C1 no-repick discipline) or anchor-freeze comments -- no such code
> path exists, this was a misread. "Correlated arm signals not filtered" -- already
> detected+disclosed via `trade_to_learn_digest.py`'s `cross_setup_same_day_side` (confirmed
> live in the 2026-07-30 LICENSE-MONITOR STATUS entry's own "WARNING CORRELATED" line).

> **Disposition:** every substantive claim across all 4 batches was either already fixed,
> already built, or intentional doctrine -- zero new code needed. Wrote 4 `<!-- DONE -->`
> triage blocks (one per batch, citing the live evidence above) so the next fire doesn't
> re-derive this. Doc-only commit (`analysis/self-audit/new-gaps-flagged.md`, +132/-0),
> curated safety gate 59/59 PASS at commit time. No params/heartbeat_core/filters/placement/
> exit/CLAUDE.md touched -- outside rail-4's scope entirely (pure analysis-log append).
> Revert: `git revert aed731f2`.

---

## [2026-07-31 ~00:59-01:15 ET] OK -- conductor (AFTERHOURS): STATE-FRESHNESS-SILENT-TASK-STALL-SELFHEAL closed, commit `33a42102`

> **STAGE 0/1:** ET 01:00 Friday (market closed). Budget gate PROCEED ($0/$30, 0/4 fires).
> `engine-health.json` showed 1 RED at fire start: `state_freshness` -- 3/17 live-path state
> files STALE (`trade-today.json`, `pnl-statement.json`, `ema-snapshot.json`). Per STAGE-1
> priority-2 (Engine RED), investigated first.

> **FOUND, live-verified (OP-33, not guessed):** `Gamma_TradeToday` / `Gamma_BrokerFills` /
> `Gamma_EmaSnapshot` all last fired 2026-07-29 despite `Enabled=True`/`State=Ready`/
> `LastTaskResult=0` (their last run succeeded), no hung process anywhere on the box
> (`Win32_Process` sweep clean), no reboot (`LastBootUpTime` 2026-07-17), `Schedule` service
> `Running` the whole time, `NumberOfMissedRuns` nonzero (195/43/1 -- Task Scheduler itself
> knew it missed occurrences) and a manual `Start-ScheduledTask` succeeded immediately. A
> wider `Get-ScheduledTaskInfo` sweep found ~17 more `Gamma_*` tasks in the identical
> last-ran-2026-07-29 shape (trigger times spanning 07:46-15:30 local) while dozens of OTHER
> tasks -- including 1-min-cadence `Gamma_HeartbeatCore` -- fired normally all through
> 2026-07-30, ruling out a machine-wide sleep/reboot/AV cause. **Root cause of WHY Task
> Scheduler silently stopped dispatching these triggers was NOT determined** -- the
> `Microsoft-Windows-TaskScheduler/Operational` event log is disabled on this box, zero
> forensic trail available. Rather than over-invest chasing an unfalsifiable Windows mystery,
> filed the open question as a lesson with a queued (not executed) follow-up: re-enable that
> event log so a recurrence leaves evidence.

> **FIX SHIPPED (remediation, not the forensics):** `state_freshness_selfheal.py` -- for any
> RED `state_freshness_audit` entry, resolves the manifest's `task` field to a single
> `Gamma_*` task name and force-starts it via `Start-ScheduledTask` (cooldown-guarded 20min,
> fail-open, never guesses an ambiguous/manual/multi-writer field). Wired into the existing
> 5-min `Gamma_TvWatchdog` cadence (`run-tv-watchdog.ps1`, no new scheduled task) --
> structurally the SAME self-heal shape `Invoke-LevelRefreshSafe` established for
> `key-levels.json` on 2026-07-30, but for a genuinely different failure mode: there was no
> stuck process to kill here, the scheduled trigger itself silently never fired, so the fix
> is a direct force-start rather than kill-tree+relaunch. **Manually ran the real (non-dry-run)
> heal live tonight:** all 3 producers restored (`Start-ScheduledTask` returncode 0 each,
> output files' mtimes updated within seconds), `state_freshness_audit` verdict flipped
> RED -> GREEN, confirmed via a fresh audit re-run.

> **Verified (OP-33):** 20 new guard tests (`test_state_freshness_selfheal.py` -- resolve/
> skip-ambiguous/cooldown/dry-run/fail-open-on-audit-raise/logging), all green; full related
> suite (level-refresh, tv-launch-safe, engine-liveness, state-freshness) 87/87 green;
> curated safety gate 59/59 PASS. `git show 33a42102 --stat --name-status` confirms exactly
> the 3 intended files (L247 discipline): `state_freshness_selfheal.py` (new),
> `test_state_freshness_selfheal.py` (new), `run-tv-watchdog.ps1` (+33/-2 lines, one new
> wired section + a status-field addition).

> **Scope + revert:** 3 files, pure infra self-heal -- zero params/heartbeat_core/filters/
> placement/exit/CLAUDE.md touched. Revert: `git revert 33a42102`. Lesson filed:
> `_lesson-inbox/2026-07-31-scheduled-task-silent-stop-firing.md`.

---

## [2026-07-30] LICENSE-MONITOR (deploy-timing for WP-5/6/8/0)

> - #1 ATM (Safe-2)=YELLOW(ELIGIBLE); #1 ATM (Bold)=YELLOW(ELIGIBLE); #2 ATM=YELLOW(ELIGIBLE); #4 ATM=YELLOW(ELIGIBLE)
> - **Trade-to-learn cumulative (since arm, real fills, Rule-9 visibility-only):**
> -   bollinger_squeeze (armed 2026-07-02): since-arm 6tr $+36.00 ($+6.00/tr, 50.0% WR) [4d/4 day+side buckets -- 6 rows are NOT independent trials]
> -   double_bottom_base_quiet (armed 2026-07-01, 29d ago): 0 fills since arm — no live signal yet
> -   vwap_reclaim_failed_break (armed 2026-07-01): since-arm 2tr $-15.00 ($-7.50/tr, 50.0% WR)
> -   WARNING CORRELATED: 2026-07-28 side=P fired in BOTH bollinger_squeeze+vwap_reclaim_failed_break -- same underlying day-call, not independent
> - Files: `automation/state/license-monitor-last.json`, `backtest/autoresearch/license_monitor.py`.

---

## [2026-07-30] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-06-17..2026-07-23), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-07-23). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=YELLOW
> - **Books:** Safe2_ATM_1+2+4=RED ($-276.48); Bold_ATM_1+2=YELLOW ($-166.9)
> - **edges_confirmed_on_recent = False** (any RED=True). All live tiers still small-n / not-yet-confirmed on the freshest weeks — full-OOS-2026 base remains the larger-n companion read; HOLD capital scaling until an edge CONFIRMs. RED-BLOCKED: Safe2_ATM_1+2+4 — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-07-30 ~20:30-20:50 ET] OK -- conductor (AFTERHOURS): LEVEL-REFRESH-WATCHDOG-WINDOW-BUG closed, commit `d7774638` -- plus closing the visibility gap on 4 earlier undocumented fixes

> **STAGE 0/1:** ET 20:30 Thursday (market closed). Budget gate PROCEED ($1.98/$30, 1/4
> fires). `engine-health.json` showed 2 RED checks at fire start: `levels_blind` (0/770 RTH
> rows today carried an active key level) and `state_freshness` (3/17 live-path files
> stale). Per STAGE-1 priority-1/2 (function-first / Engine RED), investigated first.

> **FOUND: the whole `levels_blind` incident had ALREADY been root-caused, fixed, tested,
> and doc-synthesized by 4 earlier fires TONIGHT (commits `90a0e826`, `54b27c00`,
> `3a5d3246`, `9b25aa79`, `0d70b109`, between ~19:06-20:24 ET) -- but NONE of that work was
> ever reported to STATUS.md** (only `queue.md` and a standalone doc,
> `analysis/deep-research/BLIND-ENGINE-REPAIR-2026-07-30.md`, carried it). Closing that
> visibility gap now: `Gamma_LevelRefresh`'s Task Scheduler cadence silently stalled ~20h
> (last good run 07-29 22:43 ET, zero errors, zero self-recovery); every one of today's 770
> RTH decision rows carried `levels_active: []`; the engine fell through to its worst cohort
> (trendline-only) and fired 11 unanchored `ENTER_BEAR` verdicts at the day's low before SPY
> rallied 6.7pts -- only `RISK_DENY_RISK_CAP`/`RISK_DENY_PDT` stopped the fills. Fixed with
> THREE layers: (1) `SKIP_NO_LEVELS` entry-side rail in `heartbeat_core.py` -- an ENTER with
> no level anchor now refuses instead of trading blind; (2) `Invoke-LevelRefreshSafe`
> (`_shared.ps1`) -- kill-the-stuck-tree + relaunch self-heal, wired into the existing 5-min
> `Gamma_TvWatchdog` cadence; (3) `levels_blind_check.py` -- a day-scoped, RTH-ratio,
> non-market-hours-suppressed consumer+producer monitor. Lesson filed:
> `_lesson-inbox/level-refresh-silent-stall-2026-07-30.md`.

> **THIS FIRE'S OWN FINDING (re-verifying rather than trusting the prior work, OP-33):** the
> self-heal window guard in `run-tv-watchdog.ps1` read `$mins -ge 942 -and $mins -le 955`.
> `$mins` is `Hour*60+Minute` (minutes-since-midnight) -- the SAME convention the adjacent
> `hbFlag` window correctly uses via `575`/`955`. `942` minutes-since-midnight is **15:42
> ET, not 09:42 ET** -- so the safety net built to prevent tonight's exact incident from
> recurring only ever activated in the final **13 minutes** before the close (942-955), not
> the intended ~373-minute RTH window (582-955). Its own guard test asserted the literal
> substring `"942" in src`, which is true under BOTH readings, so it could not catch this by
> construction. **Fix:** `942 -> 582` (9*60+42); test rewritten to regex-extract the real
> `$mins` bound and assert on the DECODED wall-clock time (09:42/15:55) plus a width check
> (>300min). RED-proofed via `git stash` (fails with the predicted 15:42 readout
> pre-fix); 5/5 green post-fix; full related suite (blind-no-levels,
> levels-blind-detection, tv-launch-safe) 85/85 green; curated safety gate 59/59 PASS.
> `git show d7774638 --stat --name-status` confirms exactly the 2 intended files (L247).
> Lesson filed: `_lesson-inbox/substring-guard-cant-verify-magic-number-semantics-2026-07-30.md`
> (C14 family: a unit-bearing magic-number guard must assert the DECODED value, not the
> substring's presence).

> **Scope + revert:** 2 files, pure watchdog infra -- no params/heartbeat_core/filters/
> placement/exit/CLAUDE.md touched. Revert: `git revert d7774638`.

> **Left open for next fire (not this fire's scope):** the synthesis doc
> (`BLIND-ENGINE-REPAIR-2026-07-30.md`) flags a separate finding worth a follow-up look --
> "49 documented-Active scheduled tasks sat `State=Disabled`" -- and a sizing-deadlock
> per-arm ceiling table with 4 ranked remediation options left UNCHOSEN. Neither touched
> here; flagging so they don't silently age out of visibility the same way this whole chain
> almost did.

---

## [2026-07-29 ~20:30-21:05 ET] OK -- conductor (AFTERHOURS): CONDUCTOR-BUDGET-CROSS-MIDNIGHT-BUG closed, commit `631798f0`

> **STAGE 0/1:** ET confirmed 20:30 Wednesday (market closed). Budget gate PROCEED ($0.04/$30,
> 2/4 fires reported -- see finding below, that count was itself wrong). `engine-health.json`
> GREEN/YELLOW (14 checks, 0 RED, gex_archive 1-day interior-gap YELLOW non-critical).
> `self-check-last.json` DEGRADED (rule-enforcement-working fill-funnel blocks, PDT-blocked bold,
> LLM-narrative-fallback premarket, trendline-draw not marked -- none a bug). Priority-3 self-audit
> gap won the pick: `analysis/self-audit/new-gaps-flagged.md` flagged "conductor firing far more
> than max_fires (4/day)" on THREE consecutive nights (07-27/07-28/07-29 17:31 entries), matching
> the prior 07-28 QUIET-EXHAUSTED entries below that speculated about duplicate scheduled triggers.

> **ROOT CAUSE, verified live (OP-33, not guessed):** Task Scheduler triggers for the whole
> `Gamma_Conductor*` family are exactly the documented cadence (3x/day for `Gamma_Conductor`,
> confirmed via `Get-ScheduledTask` -- no duplicate/rogue trigger). The real bug was in
> `setup/scripts/conductor_budget.py`'s own `spend_today()`: it matched a `conductor-outcomes.jsonl`
> row to an ET calendar day by SUBSTRING-searching the day string against the row's raw `fired_at`
> (UTC ISO) field. ET is UTC-4 in July, so the scheduled 20:30 ET evening fire on day D writes
> `fired_at` with a UTC calendar date of D+1 (20:30 ET + 4h = 00:30 UTC next day) -- so that
> fire's row leaked forward into day D+1's own budget check the next morning, silently starting
> every ET day at "1 fire already spent" (compounding with late-night fires). Live-verified the
> real bite: THIS fire's own STAGE-0 check read "2/4 fires" for 2026-07-29 before the fix; after
> the fix, `spend_today('2026-07-29')` correctly reads 0 (those 2 were 07-28's own evening/
> late-night fires that had leaked across midnight). The Task Scheduler Operational event log
> needed for direct forensics was DISABLED (`IsEnabled=False`) -- a genuine but secondary gap,
> not required for this fix, left as a follow-up if J wants that visibility restored.

> **Fix:** `_stamp_to_et_date()` converts an aware/UTC `fired_at` to its true ET calendar date via
> `et_clock.et_now(now_utc=...)` before comparing, falling back to the old substring match only
> when a stamp fails to parse (fail-open, C7). `ts_et` (already ET-local, naive) stamps pass
> through unconverted. **Bonus find:** the project's OWN existing test fixtures had independently
> fallen into the identical trap (`f"{DAY}T02:00:00+00:00"` is actually 22:00 ET the PREVIOUS
> day) -- corrected to `T16:00:00+00:00` (genuinely mid-day ET) so the fixtures test what they
> claim to. 3 new regression tests pin the exact incident shape, RED-proofed via `git stash`
> (all 3 failed pre-fix with the predicted mis-count, 13 pre-existing tests unaffected, 16/16
> green post-fix). Curated safety gate 59/59 PASS. Post-commit `git show 631798f0 --stat
> --name-status` confirms exactly the 2 intended files (L247 discipline).

> **Scope + revert:** 2 files (`setup/scripts/conductor_budget.py`,
> `backtest/tests/test_conductor_budget.py`) -- pure conductor-scheduling infra, zero trading-path
> touched (no params/heartbeat_core/filters/placement/exit/CLAUDE.md). Revert: `git revert 631798f0`.
> Lesson filed: `strategy/candidates/_lesson-inbox/ET-UTC-midnight-boundary-fire-miscounting.md`
> (generalizable rule: bucketing a UTC-stamped event by ET calendar date needs a real conversion,
> never a substring/prefix match against the raw UTC string).

> **NOTE on the 07-28 QUIET-EXHAUSTED entries below:** those are the STALE evidence this exact
> bug produced (the "5/4, 6/4, 7/4 fires" readings were themselves inflated by the leak) -- left
> in place per OP-22 (preserve the original disclosure) rather than rewritten; this entry is the
> correction. The self-audit swarm re-flagged them 3 nights running partly because they were still
> sitting fresh in this file; now resolved with a code fix, not just a note.

---

## [2026-07-28 ~20:30 ET] QUIET -- conductor (AFTERHOURS): nightly budget EXHAUSTED, zero work

> **STAGE 0 rail-0 gate:** `conductor_budget.py --check` returned exit 3 -- `7 fires today >= max_fires 4`.
> Per rail 0, exited immediately with zero model work (no queue read, no task pick, no fan-out).
> This is the FOURTH QUIET-EXHAUSTED fire today (03:30 at 4/4, 08:42 at 5/4, 18:12 at 6/4, now 20:30
> at 7/4). The counter keeps climbing well past the documented 3-fire/night AFTERHOURS cadence
> (20:30/01:00/05:30 ET) -- something is waking `conductor` extra times on 2026-07-28. Worth a
> FABLE-ESCALATION next non-exhausted fire: audit Task Scheduler history for `Gamma_Conductor*`
> triggers today and confirm whether extra manual/interactive invocations (like this one) or a
> duplicate/misconfigured scheduled trigger is the source -- 7 fires in one day is nearly double
> the 4/day cap and burns through budget before the after-hours cadence gets a real turn.

## [2026-07-28 ~18:12 ET] QUIET -- conductor (AFTERHOURS): nightly budget EXHAUSTED, zero work

> **STAGE 0 rail-0 gate:** `conductor_budget.py --check` returned exit 3 -- `6 fires today >= max_fires 4`.
> Per rail 0, exited immediately with zero model work (no queue read, no task pick, no fan-out).
> This is the THIRD QUIET-EXHAUSTED fire today (03:30 ET at 4/4, ~08:42 ET at 5/4, now ~18:12 ET
> at 6/4) -- the daily counter is climbing past `max_fires` across multiple wake sources on the
> same calendar day (2026-07-28), not resetting between them as the ~08:42 note assumed it would
> after midnight. Worth a look next non-exhausted fire: confirm which scheduled tasks are firing
> conductor beyond the documented 20:30/01:00/05:30 ET cadence (6 fires by 18:12 ET implies extra
> wakes, possibly manual/interactive invocations like this one, which still correctly count
> against the shared daily cap). Next fire after local midnight resets the counter.

## [2026-07-28 ~08:42 ET] QUIET -- conductor (AFTERHOURS): nightly budget EXHAUSTED, zero work

> **STAGE 0 rail-0 gate:** `conductor_budget.py --check` returned exit 3 -- `5 fires today >= max_fires 4`.
> Per rail 0, exited immediately with zero model work (no queue read, no task pick, no fan-out).
> Note: this is the SECOND QUIET-EXHAUSTED fire today (was 4/4 at ~03:30 ET, now 5/4) --
> the counter did not reset overnight as the prior entry assumed; it resets at local midnight,
> and this fire landed on the same calendar day. Next fire (20:30 / 01:00 / 05:30 ET cadence)
> should land after local midnight and reset.

## [2026-07-28 ~03:30 ET] QUIET -- conductor (AFTERHOURS): nightly budget EXHAUSTED, zero work

> **STAGE 0 rail-0 gate:** `conductor_budget.py --check` returned exit 3 -- `4 fires today >= max_fires 4`.
> Per rail 0, exited immediately with zero model work (no queue read, no task pick, no fan-out).
> Next fire (per cadence: 20:30 / 01:00 / 05:30 ET) resets the daily counter at local midnight.

## [2026-07-28 ~01:16-01:30 ET] OK -- conductor (AFTERHOURS): DRESS-REHEARSAL-NARROW-STRIKE-BAND closed, commit `96cf82b4`

> **STAGE 0/1:** ET confirmed 01:16 Tuesday (market closed). Budget gate PROCEED
> ($0.60/$30, 3/4 fires). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED, gex_archive
> 1-day interior-gap YELLOW non-critical). Ran `self_check.py` per STAGE-1 priority-1
> (function-first) and it reported **BROKEN**: `DRESS-REHEARSAL RED` off the real
> 2026-07-27T20:45:01 nightly artifact -- `check1_options_{safe,bold}` both RED. This
> outranked `task_scorer.py --top`'s `TWIN-DOCTRINE-FIRST-DEPLOY` (still J's REVOKE
> surface, correctly skipped again) and every queue item -- an active self-check BROKEN
> flag on the "are we good for tomorrow" probe is priority-2 CRITICAL.

> **Root cause, verified against the REAL Alpaca chain (spot 738.85):**
> `_pick_deep_otm_put` searched a fixed $10-wide strike window below the 5%-OTM target;
> SPY's far-OTM chain there is only 3 strikes (695/700/701, not $1-spaced), all pricing
> $0.06-$0.08 -- above the $0.05 ceiling -- so the probe never reached order placement on
> EITHER account, every night this happens to be the shape of the chain. Fixed: escalating
> `STRIKE_SEARCH_BANDS = (10, 30, 60, 100)`; live-verified band=30 immediately surfaces
> strike 690 @ $0.05. **Second bug found while verifying live:** `_next_trading_day`
> guessed via `calendar?start=today+1` -- correct only when called after today's close.
> My own off-schedule verification run (01:xx ET, before today's open) skipped today and
> disagreed with `check3_sanity`'s own `/v2/clock` read, false-RED-ing the very rehearsal
> I'd just fixed. Fixed by deriving `next_day` from the broker's own `clock.next_open`
> (C11: broker is the source of truth), calendar endpoint kept only as a fallback --
> this was going to leave a MISLEADING RED artifact sitting on disk for the ~8h until
> today's real open if left unfixed (self_check has no time-gate on `overall=="RED"`).

> **Verified this fire (OP-33), not claimed:** 6 new guard tests, RED-proofed via scoped
> `git stash -- setup/scripts/dress_rehearsal.py` (all 6 failed against pre-fix code with
> the exact expected pre-fix behavior/AttributeError, popped clean, 40/40 green post-fix).
> **Live end-to-end re-verification, not just unit tests:** re-ran `dress_rehearsal.py`
> for real -> `overall=GREEN` (was RED), both `check1_options` GREEN with a genuine
> ACCEPTED+CANCELED probe order on each account (order ids in the artifact); re-ran
> `self_check.py` -> `GREEN, 0 problem(s)` (was BROKEN). Curated safety gate 59/59 PASS
> both before and after the commit. Post-commit `git show 96cf82b4 --stat --name-status`
> confirms exactly the 2 intended files (L247 discipline).

> **Scope + revert:** 2 files (`setup/scripts/dress_rehearsal.py`,
> `backtest/tests/test_dress_rehearsal.py`). Zero trading-path touched (no params/
> heartbeat_core/filters/placement/exit/CLAUDE.md) -- this is the nightly rehearsal
> PROBE script, not the live entry path. Revert: `git revert 96cf82b4`.

---

## [2026-07-28 ~01:00-01:15 ET] OK -- conductor (AFTERHOURS): SAFETY-GATE-MISSES-PARITY-SUITE closed, commit `b0129034`

> **STAGE 0/1:** ET confirmed 01:00 Monday->Tuesday rollover (market closed). Budget gate
> PROCEED ($0/$30, 2/4 fires). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED,
> gex_archive 1-day-interior-gap YELLOW non-critical). Self-audit gaps: newest two batches
> (2026-07-26T17:32 4-line, 2026-07-27T17:31 12-line) are scaffold/perspective-header noise
> with no new concrete action beyond what's already tracked (budget-governor distortion
> already fixed via SELF_REPORT_CORRECTION=2.2; off-box deadman + zero-for-twelve postmortem
> already queued) -- left un-triaged rather than spending the fire on noise-disposition,
> picked the concrete HIGH item instead. `task_scorer.py --top` named
> `TWIN-DOCTRINE-FIRST-DEPLOY` (still J's REVOKE surface, propose-only, correctly skipped
> per multiple prior fires) -- next-highest ready HIGH item was `SAFETY-GATE-MISSES-PARITY-
> SUITE` (filed 2026-07-27: commit 3ced7457 broke 16 engine_cli parity cases and still
> PASSED the pre-commit gate because the suite wasn't wired in + a lying exit-code was
> trusted). Picked it -- process-integrity gap on the exact contract this whole autonomous
> loop depends on to ship safely.

> **What I built:** `backtest/tests/run_safety_gate.py` -- added `test_engine_cli_parity.py`
> to `GATE_TESTS` (curated gate 5->6 suites, still ~5s). New `_parse_pytest_counts()` parses
> pytest's summary line out of captured stdout+stderr; `run()` now FAILS if the subprocess
> exit code is 0 but the parsed summary shows `failed`/`error` > 0 (C7: audit outputs, not
> exit codes -- directly the failure mode that let the exit-0-but-17-failed incident happen).
> 10 new guard tests (`test_run_safety_gate.py`): GATE_TESTS membership, `_parse_pytest_counts`
> unit coverage (passed/failed/error/errors/no-summary), and 3 `run()`-level RED-proofs via
> `monkeypatch.setattr(gate_mod.subprocess, "run", ...)` feeding a fake `CompletedProcess`
> with `returncode=0` + a `"1 failed"` summary -- confirms `run()` returns non-zero, not 0.

> **Verified this fire (OP-33), not claimed:** RED-proofed via scoped
> `git stash -- backtest/tests/run_safety_gate.py` (single pathspec, not tree-wide): 6 of the
> 10 new tests failed against pre-fix code with the exact expected
> `AttributeError: module 'run_safety_gate' has no attribute '_parse_pytest_counts'` /
> `AssertionError: run() returned 0 (PASS) even though...` -- `git stash pop` restored
> cleanly, re-verified 10/10 green. Live curated gate re-run post-fix: `59 passed` (was
> the prior-fires' "31+5" baseline -- now includes the parity suite's 28 + this fire's own
> 10, net of the 5 originally-curated suites' counts). Post-commit
> `git show b0129034 --stat --name-status` confirms exactly the 2 intended files
> (`run_safety_gate.py` modified, `test_run_safety_gate.py` added) -- L247 discipline.

> **Scope + revert:** 2 files. Zero trading-path touched (no params/heartbeat_core/
> filters/placement/exit/CLAUDE.md) -- pure process-integrity tooling that protects every
> future autonomous commit through this same gate. Revert: `git revert b0129034`.

[2026-07-27T23:40 ET] fable-session: LADDER DISARMED ON EVIDENCE -- the fast loop worked. The 390-day replay J demanded ("prove it, don't wait for tomorrow's tape") came back an honest NULL: floor 7 = -$31,015 (1,538 tr), floor 8 = -$16,642 (725 tr), floor 9 = -$10,903 (332 tr) vs binary-engine baseline +$5,307; similar WR, much worse loss/win magnitude; day-majority + drop-best FAIL on all lanes; baseline parity byte-identical to the published scorecard. All 5 floors REMOVED (fleet accounts.json x3 + params.json + aggressive/params.json) ~6h after arming, BEFORE the open -- the machinery/guards stay intact and inert, the why-not provenance rows are the $0 forward shadow, and the crypto twin's ladder-variant SIM lane keeps accruing its own mechanism evidence 24/7. Pre-registered narrow hypothesis (score>=9 + confluence + htf BEAR -- frozen BEFORE slicing) queued as LADDER-SUBSET-PREREG. RE-ARM = restore the keys (docs at each site carry the numbers). This is process>P&L: we armed on n=10, the n=1,538 answer arrived 6 hours later, and we acted on it the same night instead of discovering it live over two weeks.
[2026-07-27T21:22 ET] fable-session: SHIPPED + ARMED overnight (J directive "stop making me prompt") -- REVOKE surface:
  1. SCORE LADDER LIVE (deb781ea): risky-3 (paper, $1,852) enters MIN-SIZE at bear_score>=7 on scoring-failed ticks w/ raw level-tied trigger + level (the 07-27 bear-9 class). BEAR only. REVOKE: delete score_ladder_floor from risky-3's gate_override in fleet/accounts.json -- next tick reverts. Evidence: analysis/arm-ladder/ARM-LADDER-V1-2026-07-27.md (n=10 anchors, SMALL -- the fleet paper ledger is the forward A/B). Other arms UNARMED pending J's table look (proposed 8/8/9/9).
  2. WHY-NOT provenance (3ced7457+79fafbe0): every tick now logs raw detections + blockers + levels + raw rejection level. "Zero triggers" can never lie again.
  3. Premarket readiness gate (98dd919a, WS2): Gamma_PremarketReadiness 09:00 ET -- fleet+MCP+levels+bias+TV+engine+task, ONE verdict, leads the morning brief.
  4. Escalation cord (36e78164, WS4): Gamma_EntryBlockWatch every 2min RTH -- bear>=8/bull>=9 + raw trigger + no entry -> ONE voice alert per episode, max 3/day. J hears the block AT the moment.
  5. Premarket level-compiler v2 (7b4aa3f4, WS1): LANDED -- SIP premarket (66 bars/744k shares vs IEX's 1 bar/80 shares on 07-27), degeneracy guard (an 80-share print can never be PMH again), 3-above+3-below directional balance, weight+zone_width on every level, daily_context.py (gap/shelf/backside-retest -- calibrated on real 07-27: gap +0.81% filled, shelf [744.18,745.78] 10 touches broken 07-23, backside_retest=true). 141 tests green, SIP-feed guard RED-proofed live.
  Trading path deltas: ladder lane only. Losses today -$571.64 (Safe -$216.44 / Bold -$355.20) -- root-caused (filter 5 structural ribbon gate; ruling + teardown in queue.md + ENTRY-BAR + G1/G2/PMH items). Kill switches never tripped.
[2026-07-27T01:00 ET] conductor: QUIET — nightly budget exhausted (5 fires today >= max_fires 4) — zero model work, rail-0 gate
[2026-07-27T01:12 ET] conductor: QUIET — nightly budget exhausted (6 fires today >= max_fires 4) — zero model work, rail-0 gate
[2026-07-27T05:30 ET] conductor: QUIET — nightly budget exhausted (7 fires today >= max_fires 4) — zero model work, rail-0 gate
[2026-07-27T06:12 ET] conductor: QUIET — nightly budget exhausted (8 fires today >= max_fires 4) — zero model work, rail-0 gate
[2026-07-27T09:12 ET] conductor: QUIET — nightly budget exhausted (9 fires today >= max_fires 4) — zero model work, rail-0 gate
[2026-07-27T18:42 ET] conductor: QUIET — nightly budget exhausted (10 fires today >= max_fires 4) — zero model work, rail-0 gate
[2026-07-27T20:30 ET] conductor: QUIET — nightly budget exhausted (11 fires today >= max_fires 4) — zero model work, rail-0 gate

## [2026-07-26 23:47 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (8 fires today >= max_fires 4) -- zero model work, exiting per rail-0

## [2026-07-26 21:48 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (7 fires today >= max_fires 4) -- zero model work, exiting per rail-0

## [2026-07-26 20:42 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (7 fires today >= max_fires 4) -- zero model work, exiting per rail-0

## [2026-07-26 20:30 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (7 fires today >= max_fires 4) -- zero model work, exiting per rail-0

## [2026-07-26 19:48 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (6 fires today >= max_fires 4) -- zero model work, exiting per rail-0

## [2026-07-26 17:48 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (5 fires today >= max_fires 4) -- zero model work, exiting per rail-0

## [2026-07-26 17:12 ET] QUIET -- conductor (WEEKEND): nightly budget EXHAUSTED (4/4 fires today) -- zero model work, exiting per rail-0

## [2026-07-26 ~15:47-16:25 ET] OK -- conductor (WEEKEND): AUDIT-BLINDSPOT-CLAUDE-NATIVE-TASKS closed, commit pending

> **STAGE 0/1:** ET confirmed 15:47 Sunday (market closed, weekend mode). Budget gate PROCEED
> ($20.35/$30, 3/4 fires -- this fire pushes toward the daily cap). `engine-health.json`
> GREEN/YELLOW (14 checks, 0 RED, gex_archive 1-day-stale YELLOW non-critical). `task_scorer.py`
> top item `TWIN-DOCTRINE-FIRST-DEPLOY` (MED, 6.5) is still J's REVOKE surface, propose-only,
> correctly not picked (Nth fire confirming). Next 3 tied at 5.0: `CATASTROPHE-CAP-WIDEN-WATCH`
> and `TRENDLINE-TIGHT-EXIT-ACCRETE` are both accrue-then-decide watch-only items (no new
> action per multiple prior fires' own notes); `OFF-BOX-DEADMAN-SWITCH` is a real but separate
> monitoring-nicety build. Per STAGE-1 priority-3 (self-audit gaps outrank queue HIGH), read
> `analysis/self-audit/new-gaps-flagged.md`'s newest un-triaged batch (2026-07-25T17:32:35, 10
> items) and found one of its 8 real (non-scaffold) lines pointed at a still-open, concretely
> actionable queue item: `AUDIT-BLINDSPOT-CLAUDE-NATIVE-TASKS` (MED) -- picked it, since closing
> it closes BOTH the queue item and the matching self-audit gap in one shot (compound, not
> accumulate).

> **What I found + built:** `audit_scheduled_tasks.py` only ever knew about `Gamma_*` Windows
> Task Scheduler entries -- Claude-native scheduled skills at `~/.claude/scheduled-tasks/`
> (a completely separate scheduling mechanism) were invisible to every governance surface,
> which is how `gamma-sniper-shadow-eod` (a daily **opus** fire, ~$100/mo) ran ungoverned for
> 2 months before the 2026-07-25 cost pass caught and retired it by hand. Built
> `_claude_native_tasks()` (enumerates `~/.claude/scheduled-tasks/*/SKILL.md`, extracts the
> `name:` frontmatter field, falls back to the dirname) wired into `audit()` as a new
> `CLAUDE_NATIVE_TASK_UNGOVERNED` flag against a new `KNOWN_CLAUDE_NATIVE_TASKS` allowlist
> (empty by design -- both prior offenders are retired, not allowlisted; a future one must be
> reviewed + added there + given a real SCHEDULED-TASKS.md row, or retired). Deliberately scans
> ONLY the live directory, never a `-retired-*` sibling. New `claude_native_registered` count
> added to the JSON summary for visibility.

> **Verified this fire (OP-33), not claimed:** 11 new guard tests
> (`backtest/tests/test_audit_scheduled_tasks_claude_native.py`) -- RED-proofed via a scoped
> `git stash -- setup/scripts/audit_scheduled_tasks.py` (all 11 failed with the exact expected
> `AttributeError`/behavior gap against pre-fix code, `git stash pop` restored cleanly,
> re-verified 11/11 green). Ran the real script against the live box: `claude_native_registered:
> 0`, no false `CLAUDE_NATIVE_TASK_UNGOVERNED` flag (the directory is genuinely empty right now
> -- both prior offenders correctly live under the `-retired-2026-07-25` sibling, confirmed by a
> direct `ls`). Curated safety gate (`run_safety_gate.py`): 31+5 PASS. `py_compile` clean on both
> touched files.

> **Also closed the matching self-audit gap:** the 2026-07-25T17:32:35 batch in
> `analysis/self-audit/new-gaps-flagged.md` had 10 un-triaged lines; appended a DONE marker
> disposing all 10 (2 scaffold headers, 1 already-ruled, 2 already-fixed via the existing
> `conductor_budget.py` `SELF_REPORT_CORRECTION=2.2` governor, 1 tracked-but-not-yet-built
> (`OFF-BOX-DEADMAN-SWITCH`), 1 closed this fire (the Claude-native-tasks gap itself), 1 tracked
> HIGH item (`ZERO-FOR-TWELVE-POSTMORTEM`), 2 synthesis-commentary noise) -- so the batch stops
> reading as open on the next fire.

> **Scope + revert:** 3 files (`setup/scripts/audit_scheduled_tasks.py`,
> `backtest/tests/test_audit_scheduled_tasks_claude_native.py` [new], plus the queue.md +
> self-audit-gaps.md doc updates). Zero trading-path touched (no params/heartbeat_core/
> filters/CLAUDE.md) -- pure observability tooling. Revert: `git revert <this commit>`.

---

## [2026-07-26 ~00:12-00:20 ET] OK -- conductor (AFTERHOURS): DRESS-REHEARSAL false-RED root-caused + fixed, commit `e370b0dc`

> **STAGE 0/1:** ET confirmed 00:12 Sunday (market closed). Budget gate PROCEED ($10.67/$30,
> 2/4 fires). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED, gex_archive 1-day-stale
> YELLOW non-critical). `self-check-last.json` verdict **BROKEN** — 2 problems: `DRESS-
> REHEARSAL RED` (fresh, un-triaged) + `ENGINE DARK ALL DAY` (already tracked as
> `OFF-BOX-DEADMAN-SWITCH`, queue.md, status:pending). Per STAGE-1 priority-2 (Engine
> RED/BROKEN flags outrank queue HIGH/self-audit-gaps/inboxes), picked the fresh
> DRESS-REHEARSAL RED to investigate + fix.

> **Root cause (confirmed, not theorized):** `Gamma_DressRehearsal` is registered
> `DaysInterval=1` (every calendar day, incl. weekends — verified via `Get-ScheduledTask`).
> Its `check3_sanity` beacon-freshness sub-check enforced a hard `<24h` threshold with
> **no weekend exemption** — unlike `engine_health.py`'s `check_sight_beacon`/
> `check_engine_core`/etc., which all carry the `market_open` -> "(market closed -- quiet
> OK)" idiom. Every Saturday/Sunday night the beacon is CORRECTLY >24h stale (last ticked
> Friday's RTH close) and the rehearsal RED'd on it forever. Tonight's artifact
> (`dress-rehearsal.json`, 2026-07-25T20:45:01, Saturday): check1/check2 (real broker
> order-acceptance + crypto round-trip) both GREEN; only `check3_sanity` RED'd, on
> "sight-beacon.json age 52.3h (must be <24h)".

> **Fix:** `check3_sanity(creds_map, next_day, *, is_weekend: bool = False)` — `main()`
> derives `is_weekend` via the canonical `et_clock.et_weekday() >= 5` (same convention as
> `is_market_hours`, no new logic invented). A stale-but-PRESENT beacon on a weekend is now
> GREEN "quiet OK"; a MISSING beacon still RED's regardless of day (genuine unknown, not
> known-quiet). 5 new guard tests (`TestCheck3SanityWeekendExemption`,
> `backtest/tests/test_dress_rehearsal.py`) — RED-proofed via a **scoped** `git stash --
> setup/scripts/dress_rehearsal.py` (single-pathspec, not tree-wide) confirming all 5 fail
> against pre-fix code with the exact expected `TypeError`/`AssertionError`, then popped
> clean. Full suite 34/34 pass. Curated pre-commit safety gate (5 suites) PASS.

> **Verified this fire (OP-33), not claimed:** re-ran `dress_rehearsal.py` live post-fix
> (real paper-broker round-trips, $0/idempotent/self-cleaning per its own docstring) —
> `overall=GREEN` (was RED), all 4 checks GREEN including `check3_sanity`. Re-ran
> `self_check.py` — `DRESS-REHEARSAL RED` problem gone; only the already-tracked
> `ENGINE DARK ALL DAY` (OFF-BOX-DEADMAN-SWITCH, untouched, correctly left alone — separate
> scope) remains. Post-commit `git show e370b0dc --stat --name-status` confirms exactly the
> 2 intended files (L247 discipline).

> **Scope + revert:** 2 files (`setup/scripts/dress_rehearsal.py`, its test file). No
> trading-path touched (params/heartbeat_core/filters/placement/exit code untouched) — this
> is an observability-instrument fix (dress_rehearsal is a nightly diagnostic, not a live
> trading path). Revert: `git revert e370b0dc`.

> **Learn:** this is the SAME lexical class as engine_health.py's existing weekend/market-
> closed exemption pattern, just not applied consistently to a sibling instrument built
> later — filed `_lesson-inbox/2026-07-26-dress-rehearsal-weekend-beacon-false-red.md` for
> `lesson-author` (generalizable: any freshness/liveness check built against a producer that
> only runs during weekday RTH needs the SAME weekend/holiday exemption idiom as
> engine_health.py, not a bespoke re-derivation — check for the idiom before shipping a new
> one).

---

## [2026-07-25 ~21:12-21:50 ET] OK -- conductor (AFTERHOURS): ZERO-FOR-TWELVE-POSTMORTEM live sample day-clustered (12 rows = 4 days), commit `9ad0a907`

> **STAGE 0/1:** ET confirmed 21:12 Saturday (market closed). Budget gate PROCEED ($22/$30,
> 2/4 fires -> this fire pushes to 3/4). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED,
> gex_archive 1-day-stale YELLOW non-critical). `task_scorer.py --top` returned
> `TWIN-DOCTRINE-FIRST-DEPLOY` again (still J's REVOKE surface, unpicked, Nth fire confirming).
> Picked up `ZERO-FOR-TWELVE-POSTMORTEM` (HIGH) again -- the prior fire's own named NOT-DONE
> step: "day-cluster the OOS trades and check how many genuinely distinct day+side buckets fed
> the sample."

> **What I found:** pulled the actual 12 CSV rows behind the "0-for-12" headline
> (`journal/trades.csv`, setup=vwap_continuation/vix_regime_dayside since 2026-07-01 arm). They
> are **4 distinct calendar days** (07-16, 07-20, 07-21, 07-22) and **4 distinct (day,side)
> buckets** -- not 12 independent trials. Two mechanisms: (a) same-day re-entries / same-signal
> TP1+runner leg splits (2026-07-20 vix_regime_dayside logged 4 rows, two sharing an IDENTICAL
> entry timestamp 09:54:19; 2026-07-21 vwap_continuation logged 2 rows both at 10:11:29); (b) on
> 2026-07-21 BOTH setups fired PUT the SAME day -- confirms in DATA the mechanism an earlier fire
> today proved in CODE (both derive `side` from the identical `session_vwap_asof` day-trend
> classifier) -- one wrong day-read counted as two setup failures.

> **Reframe (correction of surprise-magnitude, not a reversal of the disarm):** "0-for-12 at
> claimed 55-64% WR is p<1%" reframes to "0-for-4 correlated day-outcomes at the same claimed WR
> is ~1.7%-4.1%" -- still worth the disarm-and-investigate call already made, no longer a clean
> statistical-pipeline-falsification signal standing alone.

> **Graduated to code** (`backtest/autoresearch/trade_to_learn_digest.py`, commit `9ad0a907`):
> `compute_since_arm()` now reports `n_distinct_days` / `n_distinct_day_side_buckets` per setup
> + a new `cross_setup_same_day_side` field flagging when 2+ armed setups fire the same
> (date,side) -- generalizes past this one pair. `format_lines()` warns inline. 4 new guard
> tests (`backtest/tests/test_trade_to_learn_digest.py`, 13/13 pass) + fixed 1 unrelated
> pre-existing stale test (hardcoded 2026-07-18 arm-list assertion broke when today's earlier
> disarm changed params.json -- verified via `git stash` that the failure is identical with or
> without this commit, so this fix is incidental cleanup not scope creep).

> **Learn:** lesson filed
> `_lesson-inbox/2026-07-25-since-arm-fills-are-not-independent-trials.md` (generalizable:
> "N fills, X% WR" is a row count, not a trial count -- any since-arm digest needs distinct-day
> disclosure before it's used for a disarm/keep call).

> **Verified this fire (OP-33):** all dates/sides/timestamps are direct `journal/trades.csv`
> reads (quoted above), not inferred. Ran `trade_to_learn_digest.py --dry-run` post-commit --
> output matches. `pytest backtest/tests/test_trade_to_learn_digest.py -q` = 13/13 PASS. Curated
> safety gate (pre-commit hook) PASS. Post-commit `git show 9ad0a907 --stat --name-status` +
> `git status --porcelain` on touched paths confirmed clean (L247 discipline).

> **Scope + revert:** 2 files (digest script + its test file) + this STATUS entry + queue.md
> progress note + 1 new lesson-inbox item. Zero trading-path touched (no params/heartbeat_core/
> filters/CLAUDE.md). Revert: `git revert 9ad0a907`.

> **STILL OPEN (named next step):** the HISTORICAL OOS(2026) side of the original ask (day-cluster
> the 42-trade/21-trade validation-time OOS populations to quantify L174's "day+side selection"
> claim on the VALIDATION side, not the live-sample side just closed) -- needs a `detect_signals()`
> re-run over 2026 from each autoresearch script (detection only, no full sim sweep), not yet done.

> **STAGE 0/1:** ET confirmed 20:30 Saturday (market closed). Budget gate PROCEED ($22/$30, 2/4
> fires). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED; gex_archive 1-day-stale YELLOW,
> non-critical). `self-check-last.json` BROKEN flag is the known, already-diagnosed 2026-07-24
> off-box incident (`OFF-BOX-DEADMAN-SWITCH` queue item already tracks it; position_safe/bold
> confirmed flat, kill-switches armed-not-tripped -- nothing live-risk pending). `task_scorer.py
> --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again (still J's REVOKE surface, unchanged, Nth
> fire confirming). Picked the prior fire's own named NEXT STEP on `ZERO-FOR-TWELVE-POSTMORTEM`
> (HIGH) instead: audit whether `_b5_vix_regime_dayside.py`/`_edgehunt_vwap_continuation.py`
> source entry levels the same batch-only way as `orchestrator.run_backtest` (the mechanism that
> explained the RIDE_THE_RIBBON entry-layer gap).

> **What I found:** NO -- ruled out for both disarmed setups. Both entry triggers compute from
> `session_vwap_asof` (one shared implementation in `autoresearch/infinite_ammo_discovery.py`,
> imported verbatim by both scripts) -- a pure cumulative-VWAP-from-RTH-bars calc with zero
> `key_levels`/`key.levels` references in either file (grepped). There is no curated/memory-merged
> level source for either setup to diverge on, live vs backtest. Both scripts' exit sim is also
> `lib.simulator_real.simulate_trade_real` directly -- the SAME entry+1 convention
> `ENTRY-BAR-CONVENTION-RULING-2026-07-25.md` ruled live-faithful earlier today. So the
> entry-bar-convention / batch-vs-live-level-divergence hypothesis is now fully closed off for
> these two setups specifically (it only ever applied to the RIDE_THE_RIBBON family).

> **Leading remaining hypothesis (not new, already disclosed at arm-time):** params.json's own
> "L174 NOT INDEPENDENT / lift is largely day+side selection" caveat. vwap_continuation's arm-time
> evidence shows oos_n=42 (not tiny) -- which actually strengthens the selection-bias reading over
> a pure small-n one: if day+side was itself chosen post-hoc against the same data used to grade
> it, effective independent trials < nominal n, and 0-for-12 stops looking like p<1% surprise and
> starts looking like ordinary post-hoc-selection decay. Named the concrete next test (day-cluster
> the OOS trades, compare distinct day+side buckets vs the 0-for-12 sample) as NOT DONE -- research
> only, no engine implication either way yet.

> **Verified this fire (OP-33):** every claim above is a direct grep/read quote, not an inference
> (`session_vwap_asof` single-source import confirmed both files; zero `key_levels` hits confirmed
> both files; `simulate_trade_real` import+call confirmed both files; EDGE-HUNT-VERIFIED.json n/oos_n
> quoted directly). Zero files edited except `queue.md` (progress note) + this STATUS entry -- no
> code/trading-path touched, nothing to revert beyond the doc note.

> **Scope + revert:** 2 files (queue.md progress append, this STATUS entry). No commit needed
> (doc-only progress note on an already-tracked item) -- next fire: `git add automation/overnight/{queue.md,STATUS.md}` if J wants it committed, else it rides the next commit that touches these files.

> **STAGE 0/1:** ET confirmed 17:42 Saturday (market closed). Budget gate PROCEED ($14.30/$30,
> 1/4 fires). `engine-health.json` GREEN/YELLOW (14 checks, 0 RED, only gex_archive 1-day-stale
> YELLOW, non-critical). `task_scorer.py --top` returned `TWIN-DOCTRINE-FIRST-DEPLOY` again
> (still J's REVOKE surface, unchanged). Picked `ZERO-FOR-TWELVE-POSTMORTEM` (HIGH, filed today
> with the vwap_continuation/vix_regime_dayside disarm) instead: it named a concrete, doable-now
> next step (the already-RULED `EXIT-ENGINE-ENTRY-BAR-CONVENTION-AUDIT` escalation pointed at
> `engine_fullhist_replay`'s entry-layer divergence -- "matched an 11:40 live fill to a 13:55
> replay entry, 2h15m apart" -- as the next suspect after partially exonerating the entry-bar
> convention itself).

> **What I found:** reproduced the raw divergence directly (`run_backtest` on 2026-07-17): the
> batch engine fires only 2 signals that day vs 4 live fills. Then found the deeper bug: the
> anchor-matcher paired on strike+side ALONE with no time bound, so it silently accepted the
> 11:40->13:55 pairing (a genuinely different signal, not a near-miss) as a PASS -- true
> trade-level fidelity on that day is **1/4, not the previously-reported 2/4**. Root cause of the
> gap itself was already disclosed pre-fire (live sources levels from a curated + multi-day
> memory-merged key-levels.json feed; `orchestrator.run_backtest` recomputes from bars only) --
> this fire's contribution is correcting the magnitude (3/4 missing, not 2/4) and killing the
> false-positive matcher class.

> **Scope discipline (OP-33, did not over-claim):** this does NOT explain the 0-for-12 directly
> -- `vwap_continuation`/`vix_regime_dayside` were validated by a DIFFERENT harness
> (`backtest/autoresearch/_b5_vix_regime_dayside.py` + siblings), not `orchestrator.run_backtest`
> (confirmed via each script's own scope disclosure + `analysis/recommendations/
> vix_regime_dayside.json#generated_by`). Named the concrete next step in queue.md: audit
> whether that autoresearch harness family has the same batch-computed-only level source.

> **Verified this fire (OP-33):** `match_entries_by_strike_side_time` extracted top-level +
> unit-tested (2 new tests: rejects the 2h15m collision, still matches an exact-time hit) --
> `test_engine_fullhist_replay.py` 7/7 fast tests pass. Curated safety gate (31+5) PASS pre- and
> post-commit. Post-commit `git show 6b7c07ac --stat --name-status` + `git status --porcelain`
> on touched paths confirmed clean (L247 discipline).

> **Learn:** filed `_lesson-inbox/2026-07-25-anchor-matcher-strike-side-only-false-positive.md`
> -- generalizable rule: any anchor/ground-truth matcher joining on a coarse key (strike+side,
> symbol, setup name) needs a time-proximity bound, or a coincidental collision silently reports
> as a false PASS.

> **Scope + revert:** 6 files (1 fix, 1 test, 2 scorecard corrections appended not overwritten,
> 1 new lesson-inbox item, 1 queue.md progress note). Zero trading-path touched (no params/
> heartbeat_core/filters/CLAUDE.md). Revert: `git revert 6b7c07ac`.


## Kitchen
Kitchen: alive, queue 34 pending, last cook 0 min ago, today $0.00, model=scorecard-python

- [2026-07-31 04:00:01] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json

- [2026-07-31 04:00:01] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json

[2026-07-31 04:00:01] crypto-daily PASS -- digest: crypto/data/scorecards/daily/2026-07-31.md

### DEGRADED: self-check 2026-07-31T07:39:57
- CANDIDATES-UNTRACKED: 26 untracked files under strategy/candidates/ (threshold 20) -- live chef/kitchen/prospector pipeline state accumulating with no commit history / no disk-loss recovery path. Batch `git add --pathspec-from-file` + commit to clear (see STRATEGY-CANDIDATES-UNTRACKED-BACKFILL precedent, 2026-07-22).

## 2026-07-31 Premarket
- Bias: no-trade. Ribbon flat/compressed, swarm deadlocked 2-2 (confidence 25/100). VIX 17.12 MID.
- Safe equity $1160.36 / Bold equity $1197.52. Both kill-switches re-armed clean, no positions.
- Known broken: Step 5/5b/5c (chart level wipe+redraw, trendline detect+draw) SKIPPED this premarket -- USD session budget ran low (~$0.90 left of $3 cap) before reaching the TV-drawing steps. Not load-bearing for entries; J's manual chart lines untouched. Re-run `trendline-draw` skill manually if desired before open.
- [07-31 09:05 ET] TvWatchdog: tv=relaunch_kill heartbeat=na levels_refresh=none fresh_heal=ran TV up but CDP dead for 3896s - kill+relaunch
- [07-31 09:10 ET] TvWatchdog: tv=relaunch_kill heartbeat=na levels_refresh=none fresh_heal=ran TV up but CDP dead for 4196s - kill+relaunch

### BROKEN: self-check 2026-07-31T09:09:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.

### BROKEN: self-check 2026-07-31T09:13:09
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.

### DEGRADED: self-check 2026-07-31T09:17:31
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.

### DEGRADED: self-check 2026-07-31T09:26:18
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.

### DEGRADED: self-check 2026-07-31T09:39:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.

### DEGRADED: self-check 2026-07-31T10:09:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- [07-31 10:20 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 3666s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 10:20 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 3666s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 10:25 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 3966s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 10:25 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 3966s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 10:30 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 4266s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 10:30 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 4266s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 10:35 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 4566s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 10:35 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 4566s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T10:39:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 10:40 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 4866s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 10:40 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 4866s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 10:45 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 5166s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 10:45 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 5166s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 10:50 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 5466s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 10:50 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 5466s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 10:55 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 5766s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 10:55 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 5766s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:00 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 6066s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:00 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 6066s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:05 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 6366s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:05 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 6366s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T11:09:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 11:10 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 6666s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:10 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 6666s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:15 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 6966s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:15 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 6966s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:20 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 7266s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:20 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 7266s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:25 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 7566s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:25 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 7566s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:30 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 7866s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:30 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 7866s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:35 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 8166s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:35 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 8166s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T11:39:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 11:40 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 8466s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:40 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 8466s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:45 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 8766s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:45 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 8766s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:50 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 9066s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:50 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 9066s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 11:55 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 9366s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 11:55 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 9366s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:00 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 9666s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:00 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 9666s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:05 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 9966s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:05 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 9966s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T12:09:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 12:10 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 10266s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:10 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 10266s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:15 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 10566s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:15 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 10566s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:20 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 10866s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:20 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 10866s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:25 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 11166s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:25 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 11166s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:30 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 11466s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:30 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 11466s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:35 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 11766s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:35 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 11766s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T12:39:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 12:40 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 12066s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:40 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 12066s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:45 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 12366s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:45 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 12366s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:50 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 12666s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:50 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 12666s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 12:55 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 12966s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 12:55 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 12966s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:00 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 13266s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:00 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 13266s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:05 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 13566s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:05 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 13566s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T13:09:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 13:10 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 13866s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:10 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 13866s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:15 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 14166s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:15 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 14166s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:20 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 14466s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:20 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 14466s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:25 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 14766s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:25 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 14766s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:30 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 15066s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:30 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 15066s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:35 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 15366s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:35 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 15366s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T13:39:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 13:40 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 15666s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:40 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 15666s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:45 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 15966s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:45 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 15966s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:50 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 16266s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:50 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 16266s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 13:55 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 16566s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 13:55 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 16566s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:00 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 16866s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:00 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 16866s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:05 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 17166s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:05 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 17166s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T14:09:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 14:10 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 17466s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:10 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 17466s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:15 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 17766s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:15 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 17766s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:20 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 18066s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:20 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 18066s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:25 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 18366s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:25 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 18366s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:30 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 18666s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:30 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 18666s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:35 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 18966s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:35 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 18966s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T14:39:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 14:40 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 19266s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:40 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 19266s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:45 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 19566s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:45 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 19566s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:50 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 19866s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:50 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 19866s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 14:55 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 20166s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 14:55 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 20166s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:00 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 20466s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:00 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 20466s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:05 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 20766s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:05 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 20766s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T15:09:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 15:10 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 21066s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:10 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 21066s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:15 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 21366s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:15 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 21366s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:20 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 21666s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:20 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 21666s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:25 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 21966s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:25 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 21966s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:30 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 22266s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:30 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 22266s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:35 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 22566s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:35 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 22566s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### BROKEN: self-check 2026-07-31T15:39:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- TV-CDP UNREACHABLE (RED): CDP unreachable on :9222: TimeoutError: timed out -- TradingView's CDP endpoint is not responding. Premarket bias generation and named-level chart context may be degraded (2026-07-07/09 precedent: a 41+h outage produced a real 'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV (08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this persists, manually `taskkill /F /IM TradingView.exe` then run `setup\launch_tv_debug.ps1` by hand.
- [07-31 15:40 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 22866s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:40 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 22866s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:45 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 23166s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:45 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 23166s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:50 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 23466s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:50 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 23466s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 15:55 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=fresh levels_refresh=fresh fresh_heal=ran TV up but CDP dead for 23766s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 15:55 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 23766s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.

- [07-31 16:00 ET] TvWatchdog: tv=relaunch_kill_FAILED heartbeat=na levels_refresh=none fresh_heal=ran TV up but CDP dead for 24066s - kill+relaunch

### BROKEN: TV-CDP self-heal failed
- [2026-07-31 16:00 ET] Gamma_TvWatchdog: relaunch_kill_FAILED -- TV up but CDP dead for 24066s - kill+relaunch. Invoke-TvLaunchSafe ran the relaunch but Test-CdpReady still could not reach :9222 afterward. Manual check: curl http://localhost:9222/json/version; if empty, 	askkill /F /IM TradingView.exe then setup\launch_tv_debug.ps1 by hand.


### INFO: eod-analytics eod-summary used free-tier model (free-tier-primary)
- ts: 2026-07-31T20:00:27+00:00
- task: eod-summary
- date_et: 2026-07-31
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### DEGRADED: self-check 2026-07-31T16:09:57
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.

### DEGRADED: self-check 2026-07-31T16:39:57
- PARTICIPATION DEGRADED (YELLOW): below daily-min target -- safe=0/2-4 bold=0/2-4
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.

### INFO: eod-analytics analyst used free-tier model (free-tier-primary)
- ts: 2026-07-31T20:45:35+00:00
- task: analyst
- date_et: 2026-07-31
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

- [2026-07-31 21:00:01] gym-session (2026-07-31) → **YELLOW** :: see `automation\state\gym-scorecard-2026-07-31.json`
### DEGRADED: self-check 2026-07-31T17:09:57
- PARTICIPATION DEGRADED (YELLOW): below daily-min target -- safe=0/2-4 bold=0/2-4
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.

### INFO: eod-analytics manager used free-tier model (free-tier-primary)
- ts: 2026-07-31T21:30:25+00:00
- task: manager
- date_et: 2026-07-31
- route: free-tier-primary
- ok: True
- cost_usd: 0.0000

### DEGRADED: self-check 2026-07-31T17:39:57
- PARTICIPATION DEGRADED (YELLOW): below daily-min target -- safe=0/2-4 bold=0/2-4
- TRENDLINE-DRAW never marked today (2026-07-31) -- Step 5c may have silently skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.

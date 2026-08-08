## [2026-08-08T02:06 ET] CONDUCTOR: OK -- BUDGET-ROSTER-AUDIT-MAXBUDGETUSD -- commit `619f41aa` -- REVOKE surface

**Task picked (priority-4 queue MED, loop-CLOSING per the REGRESSING-trend guidance below;
nightly conductor budget was $29.15/$30 at fire start, so this fire was kept minimal --
no Agent-tool fan-out, direct execution only):** ran the roster-wide `-MaxBudgetUsd` audit
queued by the 2026-08-08T00:00 fire. Grepped all 23 values across `run-*.ps1`, checked every
plausible outlier's REAL logs before touching anything (per the queue item's own Action line).
Ruled out 2 false leads: `run-futures-heartbeat.ps1` (0.25, looks low) is a deliberately
`Disabled` task since 2026-06-17 (annotated retirement, zero fires since -- not a bug);
`run-analyst-eod.ps1` (0.60, looks low vs EOD siblings 4-6) shows 0/5 recent logs with any
budget/exit signature -- genuinely not failing.

**Found a real 3rd instance of the mis-sized-at-birth class:** `run-mcp-daily-audit.ps1`
(0.30 budget / 240s timeout). Full classification of all 42 dated logs
(2026-06-21..2026-08-07): 23 ok / 10 `Exceeded USD budget (0.3)` / 6 timeout(124) / 3 other
exit=1 -- a **45% combined failure rate**, still active as of the two most recent failures
checked (08-05 budget-exceeded, 08-06 timeout). The docstring's own "~$0.10/fire" estimate
never matched reality -- round-tripping Alpaca (Safe+Bold) + TradingView MCP tools regularly
costs 3x+ that. Fixed 0.30->0.60 budget, 240->300s timeout. Guard:
`backtest/tests/test_mcp_daily_audit_budget.py` (4 tests, mirrors
`test_scout_premarket_budget.py`'s pattern), RED-proofed via rename-and-restore (git-showed
pre-fix HEAD into place, 4/4 correctly failed with the known-broken-value assertions, restored
byte-identical via sha256). Repo-wide `-k budget` suite: 33/33 PASS. `run-mcp-weekly-audit.ps1`
also checked -- confirmed dead code (`Gamma_McpWeeklyAudit` no longer exists in the scheduler,
superseded by the daily version), correctly left untouched.

**Lesson filed** (`_lesson-inbox/2026-08-08-mcp-daily-audit-budget-4th-recurrence-graduated-to-roster-sweep.md`):
names this the 3rd independent instance of the identical mechanism in ~2 days of fires and
proposes the OP-25 graduation shape -- a standing parametrized guard that walks the whole
roster's logs and RED's on >15% budget/timeout failure rate, so the 4th recurrence (if any)
trips automatically instead of requiring another manual grep-and-fix sweep.

**Commit verified exactly-scoped:** `git show 619f41aa --stat --name-status` = 4 files (1
script edit, 1 new guard test, 1 queue.md status flip, 1 new lesson) via `commit_scoped.py` --
zero absorption of any other concurrent lane's staged files.

**REVOKE:** `git revert 619f41aa` (clean, 4 files, byte-revertible).

Cost this fire: ~$2.70 (log archaeology across 5 candidate tasks + guard build + RED-proof +
commit; kept deliberately lean given nightly conductor budget was near its $30 cap at start).

---

> **Autonomy metric trend: REGRESSING** (`conductor_outcome.py metric`, 20-fire window,
> net_improvement=83, cost_per_drained=$0.64, zero regressions). This fire picked a
> loop-CLOSING item (a queue item marked `done`) per the metric protocol's own guidance.

## [2026-08-08T00:00 ET] CONDUCTOR: OK -- EOD-FLATTEN-LLM-PROMPT-EXIT1 -- commit `d8ec25d2` -- REVOKE surface

**Task picked (priority-4 queue MED, self-generated, top-scored ready item per `task_scorer.py`
tied with a stale-J-ping item; picked this one per the tiebreak -- closes a loop over a
re-ping):** budget gate PASSED ($0/$30, 0/4 fires pre-fire). Engine health GREEN, market
closed (weekend). Triaged the 2026-08-07T17:32 self-audit gap batch first (priority-3) --
no single concrete NEW bounded item (each line checked against live code: order-idempotency
already exists in `heartbeat_core.py`, self_check.run() already has partial e2e coverage,
Alpaca-Greeks-fallback is a 4th consecutive-day recurrence with still no concrete secondary
source, cost-governance is partial via `conductor_budget.py`) -- appended a TRIAGED note,
zero code change.

**Main task:** root-caused `EOD-FLATTEN-LLM-PROMPT-EXIT1` (filed 2026-08-06, deliberately
left open pending live-log evidence). Read `automation/state/logs/eod-flatten{,-aggressive}-
<date>.log` directly for 08-03..08-07: every failing tick printed `Error: Exceeded USD budget
(1)` verbatim. `run-eod-flatten-aggressive.ps1` failed 5/5 dates; `run-eod-flatten.ps1` (safe)
failed 3/5 (08-05/06/07). Same class as the 2026-08-06 Scout premarket budget fix -- `$1` was
never realistic headroom for `eod-flatten.md`'s retry-until-zero close loop (up to 3 attempts
x ~4 MCP calls) + fill-reconciliation pass, mis-sized at birth (2026-06-21), not a
regression. NOT a realized safety incident -- deterministic `Gamma_EodFlattenCore` backstops
both accounts and fires first, confirmed flat every date checked.

**Fixed:** raised both scripts' `-MaxBudgetUsd` 1->2 (matches futures-eod/futures-premarket).
Guard `backtest/tests/test_eod_flatten_budget.py` (4 tests, mirrors
`test_scout_premarket_budget.py`'s pattern), RED-proofed via rename-and-restore (git-showed
pre-fix HEAD into place, all 4 correctly failed with the known-broken-value assertion,
restored byte-identical via sha256, re-confirmed 4/4 green). Curated safety gate 59/59 PASS,
sibling budget guards (scout + conductor) 22/22 green. Zero trading-path files touched
(rail-4 N/A -- backstop LLM path, not `params*`/`heartbeat_core`/`filters`/placement/exit).

**Lesson filed** (`_lesson-inbox/2026-08-08-eod-flatten-budget-misized-third-recurrence.md`):
names this the **3rd recurrence in ~1 week** of the "budget mis-sized at birth" class (Scout
08-06, this 08-08) and flags that `BUDGET-ROSTER-AUDIT-MAXBUDGETUSD` (queued MED,
`status:pending`, unactioned since 08-06) should graduate from a one-time audit to a standing
roster-wide guard per OP-25's re-violation rule -- next fire's bounded pick.

**Commit verified exactly-scoped:** `git show d8ec25d2 --stat --name-status` = 5 files (2
script edits, 1 guard test, 1 lesson, 1 self-audit triage note); `commit_scoped.py` confirmed
zero absorption of the ~20 other files sitting staged in the shared index from concurrent
lanes (L271/C34 discipline).

**REVOKE:** `git revert d8ec25d2` (clean, 5 files, byte-revertible).

Cost this fire: ~$3.90 (log archaeology across 2 accounts x 5 dates + guard build + RED-proof
+ self-audit triage + commit).

---

## [2026-08-07] RECENCY-CONFIRMATION (confirm-before-capital gate) — CONFIRMED on the freshest 25 trading days (2026-07-02..2026-08-06), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-08-06). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=YELLOW; #1 ATM (Bold)=YELLOW; #2 ATM=YELLOW; #4 ATM=CONFIRM
> - **Books:** Safe2_ATM_1+2+4=CONFIRM ($1304.16); Bold_ATM_1+2=YELLOW ($2017.9)
> - **edges_confirmed_on_recent = True** (any RED=False). CONFIRMED: #4 ATM.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-08-07T20:30 ET] CONDUCTOR: QUIET -- nightly budget gate EXHAUSTED (corrected spend $34.54 >= cap $30.00, raw self-report $15.70 x2.2) -- zero model work this fire per rail-0

## [2026-08-07T16:34 ET] CONDUCTOR: OK -- SCOUT-PREMARKET-FRESHNESS-CHECK -- self-audit gap (2026-08-06 batch) fixed+shipped -- REVOKE surface

**Task picked (priority-3, self-audit gap, `analysis/self-audit/new-gaps-flagged.md`
2026-08-06 batch, the one concrete non-scaffold line):** "Scout premarket macro/news scanner
repeatedly fails due to a low USD budget, leaving scout_output.json stale and biasing
downstream regime/bias decisions." Investigated with evidence: `Gamma_ScoutPremarket` (05:30
ET) DOES fire every weekday (live-verified `Get-ScheduledTaskInfo`: LastRunTime 8/7 03:30 MT,
LastTaskResult=0), but it is LLM-agent-driven, not a deterministic script -- its own fire log
`scout-log.jsonl` has only 9 entries across 2026-05-20..2026-08-07, including a full SILENT
MONTH (2026-06-19..2026-07-21). Task-Scheduler exit=0 is not evidence the agent actually
regenerated `scout_output.json` that day (C7) -- **nothing verified the consumed artifact
itself** until this fire. Shipped `self_check.check_scout_premarket_fresh()` (mirrors the
2026-08-03 `check_regime_stamp_daily` pattern), wired into `self_check.run()`, DEGRADED-only
(scout is a Premarket-bias addendum, non-load-bearing). 9 new guard tests
(`backtest/tests/test_self_check_scout_premarket_freshness.py`), RED-proofed via `git stash`
(8/8 fail without the fix, restored byte-identical, sha unchanged), curated safety gate 59/59
PASS, self_check test suite 147/147 PASS, live-verified clean against today's real
`scout_output.json` (fresh, correctly zero problems -- no false positive). Also closed the
adjacent 2026-08-05 self-audit batch in the same triage pass (3 scaffold headers + 5
already-tracked/not-bounded items, none newly actionable) -- see the DONE marker in
`new-gaps-flagged.md` for the full disposition, including the noted 3rd-consecutive-day
recurrence of "single Alpaca Greeks endpoint returning `{}`, needs a fallback source" (named
as genuine future work, no concrete secondary source identified yet -- not queued blind).

**REVOKE:** `git revert a2f59b87` (2 files, additive-only: 1 new function + wiring line in
`self_check.py`, 1 new guard test file; no downstream consumer besides `self_check.run()`'s
own `problems` list).

Cost this fire: ~$3.05 (read-heavy investigation + 1 file build + guards + RED-proof + commit).

---

## [2026-08-07T16:15:05 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-07 -- 5 GREEN / 0 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 137 tick(s) showed in_trade>0. 40 real fill(s) dated 2026-08-07: safe-2@09:46, bold-2@09:46, safe-2@09:47, safe-3@09:47, risky-1@09:47, risky-3@09:47, bold-2@09:47, safe-2@09:48, bold-2@09:48, safe-2@09:49, bold-2@09:49, safe-2@09:50, bold-2@… |
| WS6 regime stamp | GREEN | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-08-07, generated_at_et=2026-08-07T08:40:03-04:00 (hhmm=08:40, in 08:15-08:40 window=True). today-bias.json date=2026-08-07, regime_context.stamp_date=2026-08-07 (present=True, dates_match=True). one_liner='Yesterday 2026-08-06 (Thu) = range-chop (range 0.57%, gap +0.06%,… |
| WS3 level hysteresis | GREEN | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 66 distinct near-price levels. Worst: 771.77 flipped 4x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 171 level-refresh run(s) logged (171 ok), hysteresis_held fired 42 time(s) across 3 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-07 window_end=2026-08-06 (baseline window_end=2026-07-31, advanced=True). bear now: RED n=12 (delta +2 vs baseline n=10) exp=$-40.75/tr, verdict_moved=False. bull now: UNDERPOWERED n=8 exp=$105.75/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-08-07T16:00:05 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2', 'risky-3']. 368 theta-clock row(s) dated 2026-08-07 across 5 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=368, unavailable=0. sti… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-07 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-07`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## [2026-08-07T06:35 ET] CONDUCTOR: VBS-WRAPPER blast-radius audit + CryptoTwin live regression found+fixed (13 more templates fixed) -- REVOKE surface

**Task picked (priority-4, HIGH queue item VBS-WRAPPER-EXIT-CODE-BLIND-SPOT, top-ranked
ready item per `task_scorer.py`):** ran the `/fable-blast-radius` pass its own text had
deferred twice. **Verdict on the CORE ask (flip `run_exe_hidden.vbs` to synchronous):
NOT RECOMMENDED.** Live-enumerated all ~108 `Gamma_*` tasks on the wrapper -- every one uses
`MultipleInstances=IgnoreNew`, currently toothless fleet-wide because the fire-and-forget
`shell.Run` always returns instantly. Flipping to synchronous would make BOTH `IgnoreNew`
AND `ExecutionTimeLimit` enforceable for the first time, simultaneously, fleet-wide --
including `Gamma_HeartbeatCore` (`PT1M` limit) and 10+ other fast-cadence tasks. A heartbeat
tick that occasionally runs long would go from "always survives" to "Task Scheduler kills the
process tree mid-tick" -- a brand-new failure mode on the single most safety-critical script
in the repo. Recommending against the blanket flip; the proven safer alternative (per-task
migration onto the `run_cmd_hidden.py` relay) stays the standing path.

**While auditing, found a CONCRETE live regression, not just a hypothetical:** `Gamma_
CryptoTwin` was migrated onto the relay imperatively on 2026-07-14 (`fix-venv-pythonw-
console-leak.ps1`), but its own declarative install script (`install-crypto-twin.ps1`) was
never updated to match -- its 2026-08-01 cadence-tune re-run silently reverted the fix with
zero symptom. Generalized via a new static guard (`backtest/tests/test_install_script_relay_
wiring_drift.py`, no live Task Scheduler calls, mirrors `test_scheduled_tasks_doc.py`'s
precedent) -- found **13 MORE tasks with the identical latent bug** (`BrokerFills,
Confluence, DressRehearsal, EmaSnapshot, FirmBrief, FreeModelAudit, FuturesMirror,
LevelMemory, Prospector, TradeAutopsy, TradeToday, Trendlines, TwinSentinel`). Fixed all 14
templates (mechanical, identical substitution: route through `wscript -> vbs -> system-
pythonw -> run_cmd_hidden.py --cwd <repo> -- venv-pythonw <target.py>`). Live-verified
end-to-end for CryptoTwin (re-registered live + `Start-ScheduledTask`): `run-cmd-hidden-
2026-08-07.log` shows `exit=0 (off-desktop)` for `crypto_twin_health.py --live` (first real
exit code ever captured for this task) and `twin-health.json` shows a fresh tick
(`last_action=MANAGED`, `last_error=None`) -- underlying function unaffected. The other 13
were fixed in template only (live state already matched; re-registering was unneeded churn).

**RED-proofed the guard itself** (a genuine catch during RED-proofing, not routine): the
naive `"run_cmd_hidden.py" in text` substring check falsely PASSED against the restored
pre-fix `install-crypto-twin.ps1` because its own docstring says "no run_cmd_hidden.py hop
needed" in prose -- fixed by stripping PS1 comments/docstrings before checking, re-confirmed
RED against the reverted file, restored fixed version byte-identical (sha256 verified).
15/15 parametrized (14 pass + 1 informational skip, `Gamma_SelfAudit` has no dedicated
install script). Curated tests + adjacent suites green (`test_crypto_twin_reaper_exemption.py`,
`test_scheduled_tasks_doc.py`, both clean).

**Precisely re-scoped the remaining gap:** exactly 31 tasks (not "~90") route via the vbs
with NO relay at all; `Gamma_EodFlattenCore`/`Gamma_JIntentExecutor` deliberately EXCLUDED
from tonight's scope (safety-critical/daemon shape -- own dedicated fire, not a blind batch).
Remaining ~22 filed as the next bounded step in queue.md's VBS-WRAPPER entry. Zero
trading-path files touched (pure infra/install-script hygiene). Lesson filed:
`_lesson-inbox/2026-08-07-imperative-fix-vs-declarative-source-drift.md`.

**REVOKE:** `git revert <this commit>` (14 install-script edits + 1 new guard test file,
byte-revertible, additive-only; the CryptoTwin re-registration can be reverted live by
re-running the pre-fix action or simply re-running the old `install-crypto-twin.ps1` from
git history if ever needed, though doing so would reintroduce the exact bug this fire fixed).

---

## [2026-08-06] LICENSE-MONITOR (deploy-timing for WP-5/6/8/0)

> - #1 ATM (Safe-2)=YELLOW(ELIGIBLE); #1 ATM (Bold)=YELLOW(ELIGIBLE); #2 ATM=YELLOW(ELIGIBLE); #4 ATM=YELLOW(ELIGIBLE)
> - **Trade-to-learn cumulative (since arm, real fills, Rule-9 visibility-only):**
> -   bollinger_squeeze (armed 2026-07-02): since-arm 9tr $+68.00 ($+7.56/tr, 55.6% WR) [6d/6 day+side buckets -- 9 rows are NOT independent trials]
> -   double_bottom_base_quiet (armed 2026-07-01, 36d ago): 0 fills since arm — no live signal yet
> -   vwap_reclaim_failed_break (armed 2026-07-01): since-arm 3tr $-99.00 ($-33.00/tr, 33.3% WR)
> -   WARNING CORRELATED: 2026-07-28 side=P fired in BOTH bollinger_squeeze+vwap_reclaim_failed_break -- same underlying day-call, not independent
> - Files: `automation/state/license-monitor-last.json`, `backtest/autoresearch/license_monitor.py`.

---

## [2026-08-06T20:58 ET] CONDUCTOR: fleet replay harness REDs 5/8 fixed, root-caused -- REVOKE surface

**Task picked (priority-2, STATUS `### BROKEN:` flag):** the "6 pre-existing REDs, unowned"
fleet replay/anchor failures flagged just above by Lane 1 tonight. Root-caused with concrete
evidence (not guessed) via direct `plan_entry` reproduction: `fleet_executor._effective_passed()`
requires `block['score_peak_passed']` (not `block['passed']`) for any arm carrying
`gate_params.hard_skip_verdicts` (risky-3 only, since 2026-07-23's GATE-TIERS-IMPLEMENT ship,
even an EMPTY list flips the branch) -- `backtest/replay_fleet_arms.py`'s `_synth_signal` never
populated that field, silently zeroing risky-3's entire signal-driven replay (raw_enters={}
unconditionally) for 13 days undetected. Fixed (`_score_peak_passed_for_verdict`, mirrors
`build_shared_signal._score_peak_check` exactly) -- risky-3: matched 0/16 -> 16/16; incidentally
also resolved risky-1's misdiagnosed "window-truncation" extra=1 note (same bug), ratchet
tightened + promoted into the strict pin. Also found + fixed 2 MORE REDs not in the named 6:
`test_fleet_arm_parity.py`'s ATM-strike-at-$2K assertions were stale against THE SAME EVENING's
earlier risky-3 tier-kill (3ac1d7b2) -- that ship's own vary-and-assert guard didn't cover this
file. **Net: fleet-suite REDs 5 -> 3.** Curated safety gate 59/59 PASS, RED-proofed both fixes
(git stash both directions, exact prior AssertionErrors reproduced). Commit `9c302f99` -- test-
harness-only, zero production trading-path files touched, places no orders.

**Remaining 3 REDs (`test_anchor_pass_rate_clears_threshold[safe-3|risky-1|risky-3]`, 54-68%
vs 70% threshold) are a DIFFERENT, genuinely separate mechanism** (exit-walk fidelity via
`backtest/tools/fleet_arm_replay.py::run_anchor_validation`, not entry-timing / not touched by
either fix above -- confirmed via code read: no `plan_entry`/`_synth_signal` call in that path
at all) -- narrowed scope + evidence queued as `FLEET-ANCHOR-EXIT-WALK-FIDELITY-DRIFT (HIGH)`
in queue.md rather than rushed here (one bounded task). Lesson filed:
`strategy/candidates/_lesson-inbox/2026-08-06-replay-harness-score-peak-passed-gap.md`.

**REVOKE:** `git revert 9c302f99` (3 test/harness files, byte-revertible; no downstream
consumer of these tests other than CI/the conductor's own gate).

## [2026-08-06T20:15 ET] LANE 1 FIX+SHIP: S1-S4 executed -- SAMEBAR shipped DISARMED (day-0 replay killed the arm), risky-3 tier kill EXECUTED -- REVOKE surface

**S1 -- sizing-miss wiring guard un-staled** (`36acbbab`). Root cause: the TEST was stale, not
the code -- `c2cb9f72` (2026-08-03) deliberately shipped shrink-not-deny, so a sizing miss at
an affordable premium now legitimately ALLOWs at max_affordable_qty; the guard still pinned the
pre-ship DENY contract. Updated to pin the NEW distinguishability shape (miss -> ALLOW + shrink
note; deadlock -> RISK_CAP + binding.deadlock=True). RED-proofed (shrink disabled -> 1 RED),
restored byte-identical (sha256 2c04004b...), 7/7 green. REVOKE: `git revert 36acbbab`.

**S2 -- FLEET-SAME-BAR-COOLDOWN: wired, then DISARMED by its own ship gate** (prereg
`55880b45` committed BEFORE wiring `7598c20d`; `git merge-base --is-ancestor` proven).
The sanctioned proof FAILED: replaying each real fleet entry through the PRODUCTION trigger-bar
identity (row's own core_tick_id -> core-decisions trigger_bar_et -- exactly what the live
consult keys on) shows Wed 08-05 trigger bars ADVANCE on every re-entry (blocks NOTHING, study
claimed +$202) and Tue 08-04's only same-bar pair is risky-3 09:54/09:57 (both bar 09:45) --
so it blocks the **09:57 763C +$524 real-fills winner** the study said it preserves
(EOD-2026-08-04-ENGINE.md:464). The study keyed entries to WALL-CLOCK last-closed bars; engine
bar identity lags tick-phase-dependently (L251 class; lesson filed to _lesson-inbox). Net on
the motivating tape -$524 = the prereg's own kill criterion met on day 0. SHIPPED DISARMED:
`fleet_live.FLEET_SAME_BAR_COOLDOWN = False` (default pinned by
`test_fleet_same_bar_cooldown.py::test_default_is_disarmed_do_not_arm_verdict`); consult+stamp
code + trigger_bar_et signal plumbing (additive) land for an honest forward re-measure. Guards
8 new tests; RED-proofed (consult disabled -> 2 RED incl. the inverted parity pin), restored
byte-identical (sha256 31e0c692...). Outcome record:
`analysis/recommendations/fleet-same-bar-cooldown-OUTCOME-2026-08-06.json`.
REVOKE (of the disarmed code itself): `git revert 7598c20d`. ARM (needs the re-measure to
clear prereg gates first): flip the flag True.

**S3 -- ATM-TIER-EXTENSION pre-registered KILL executed on risky-3 ONLY** (`3ac1d7b2` +
follow-up `f3a30ad8`). Kill bar (atm-tier-extension-2k10k-prereg-2026-08-03.json: n>=10
fills, net<0) MET by risky-3 (n=14, -$653); NOT met by risky-1 (n=11, +$903). The prereg's
one-line revert edits the SHARED V15_BOLD_CORE_TIERS (would kill core bold-2 + j_intent +
risky-1 + safe-3 too), so the per-arm kill ships as new `V15_BOLD_CORE_PRE_EXT_TIERS` +
`_tiers_for_arm` branch `bold_core_pre_ext` + risky-3 accounts.json patch. Quoted at $5K:
BEFORE risky-3 ATM/strike(C,748)=748 -> AFTER OTM-2/750; risky-1 ATM/748 both before+after;
$0-2K band (2026-08-01 extension) unchanged ATM. Vary-and-assert guard 6/6; RED-proofed
(accounts.json flipped back -> 1 RED), restored byte-identical (sha256 4f14e77d...).
C14 second-consumer miss caught SAME SESSION: `fleet_arm_replay._NAMED_TABLES` didn't know
the new name (2 replay tests died on ValueError) -- fixed in `f3a30ad8`, 2/2 green.
UN-KILL (one line): risky-3 params_patch.strike_tier_table back to 'bold_core'.

**S4 -- ghost workflow wf_6db746c8-a74: VERIFIED ALREADY DEAD, transcripts preserved.**
TaskStop attempted on all 5 non-terminal agent ids -> "No task found" every one; full
Win32_Process scan shows ZERO processes surviving from the 01:39-02:50 / 09:31-10:41 spawn
windows. The "4 agents, idle 391.9m" liveness report derives from transcript mtimes (last
write 12:41 ET; 19:13-12:41 = 392m exactly), not living processes -- the run is a
transcript-only remnant in `~/.claude/projects/.../subagents/workflows/wf_6db746c8-a74/`.
Nothing killed because nothing was alive; transcripts NOT deleted per instruction.

**Suites after every ship:** fleet 378/378 (x3 runs), curated safety gate 59/59 (x3),
touched test files green (quoted per ship in SHIP-LOG-2026-08-06-EVENING.md).

## Known broken

- [2026-08-08T01:xx ET] BXM-GATE-PROBE-HEADER-DRIFT: `backtest/tests/test_bxm_gate_probe.py::
  test_probe_runs_end_to_end_without_crashing` RED (found incidentally while running the
  curated safety gate during an unrelated VBS-WRAPPER fire -- not caused by that fire, zero
  overlap in touched files). **Root cause (one sentence, verified via `head -1
  journal/trades.csv`):** `journal/trades.csv` gained a new trailing column
  (`theta_at_entry`, added by the 2026-08-01 THETA COCKPIT build) AFTER `account_id`, so
  `bxm_gate_probe.py::_load_real_trades`'s fixed `header[-1] == "account_id"` assertion
  (a defensive check added for the L239-adjacent stray-field class) now correctly catches a
  REAL header-shape change and refuses to guess -- fail-closed working as designed, but the
  probe itself needs updating to read `account_id` by NAME/fixed-relative-position now that
  it is no longer the last column, not `[-1]`. NOT fixed this fire (rail 3, out of scope for
  the VBS-WRAPPER task in progress) -- next-fire pick, queued below (BXM-PROBE-TRADES-CSV-
  HEADER-DRIFT-FIX). No trading-path/live impact: this is an offline research probe, not a
  producer trades.csv itself writes correctly with the new column.

- [2026-08-07T16:26:31.638689] CATASTROPHE-CAP-SHADOW-LEDGER: n_fires reached 13 (>= 10) -- ready for the pre-registered widen decision queued as CATASTROPHE-CAP-WIDEN-WATCH. NOT itself a verdict. See analysis/recommendations/catastrophe-cap-shadow-ledger.jsonl.
- ~~Fleet replay harness: 6 pre-existing REDs, unowned~~ **ALL 6 NOW FIXED.** 3 of 6 fixed
  2026-08-06T20:58 ET (commit `9c302f99`, see CONDUCTOR entry above). **The remaining 3
  (`test_fleet_arm_replay.py::test_anchor_pass_rate_clears_threshold[safe-3|risky-1|
  risky-3]`) FIXED 2026-08-07T01:13 ET** -- see CONDUCTOR entry below, commit `3d9228d4`.
  Root cause was NOT an exit-walk mechanism bug (the scope note's own leading hypotheses
  were checked and refuted) -- it was a metric-denominator conflation: OPRA-cache data
  gaps were being counted as automatic fidelity FAILs. Fleet-suite REDs 3 -> 0.

## [2026-08-07T01:13 ET] CONDUCTOR: fleet anchor pass-rate root-caused + fixed (denominator
conflation, NOT an exit-walk bug) -- REVOKE surface

**Task picked (priority-2, STATUS `## Known broken` flag):** the 3 remaining
`test_fleet_arm_replay.py::test_anchor_pass_rate_clears_threshold[safe-3|risky-1|risky-3]`
REDs left open by tonight's earlier fix (commit `9c302f99`), explicitly scoped as "a
genuinely separate exit-walk-fidelity mechanism ... needs an owner + a dedicated fire."

**Investigated live, not guessed.** Checked the scope note's own two named candidate
mechanisms in order: (1) trigger_level resolution -- confirmed `_load_arm_trigger_levels`
IS mostly-null (28/24/29 non-null of ~5017 decisions.jsonl rows per arm), but splitting the
anchor pass-rate BY trigger_level presence directly REFUTED it as the cause: rows *without*
a matched trigger_level had a HIGHER pass rate (89-94%) than rows *with* one (75-100%), and
neither bucket individually explained the 54-68% overall number. (2) OPRA contract-bar cache
staleness -- confirmed this IS the cause: `run_anchor_validation` computed
`pass_rate = n_pass / n_anchors` where `n_anchors` counts ALL mined real fills, but rows
with `replay_status != "OK"` (no OPRA cache for that symbol/date, or no SPY day) are never
even handed to `walk_exit_manager` -- they carry no `anchor_pass` verdict, yet the shared
denominator silently counted every one as a FAIL. Measured: safe-3 8/34 data-gap rows,
risky-1 14/37, risky-3 18/54; among rows that COULD be replayed, fidelity was
**88.5% / 87.0% / 94.4%** -- all comfortably above the 70% `ANCHOR_PASS_THRESHOLD`. The
exit-walk mechanism was never broken.

**Fixed:** `pass_rate` now divides by `n_replayable` (OK-status rows only, fidelity-only
metric). Added `n_replayable` / `n_data_gap` / `opra_coverage_rate` / `coverage_note` as
separate, still-visible fields (C7 discipline -- the coverage gap itself stays disclosed,
it just no longer contaminates the fidelity number it doesn't belong in). All 3 arms now
read `unvalidated: False`.

**RED-proofed via rename-and-restore** (L238, never git stash): reverted
`fleet_arm_replay.py` to its pre-fix HEAD version via `git show HEAD:... >`, confirmed the
existing test AND a new regression test (`test_anchor_pass_rate_denominator_excludes_
data_gaps`, pins the exact bookkeeping identity + proves the fixed rate exceeds the buggy
formula whenever a data gap exists) both fail correctly (6/6 RED, `KeyError` on the missing
new fields), restored the fix byte-identical (sha256 `28b578c8...`), re-confirmed 23/23
green. Sibling suites (`test_bold_fullhist_replay.py`, `test_replay_fleet_arms.py`) 20/20
green, curated safety gate 59/59 PASS. `git show 3d9228d4 --stat --name-status` confirms
exactly the 2 intended files (L247 discipline). Zero trading-path files touched --
test-harness/measurement-tool only, places no orders.

**Lesson filed:** `_lesson-inbox/2026-08-07-anchor-pass-rate-data-gap-conflation.md` --
names the generalizable rule (any "X/Y reproduces" ratio that treats "couldn't attempt" the
same as "attempted and failed" will misdiagnose a coverage gap as a mechanism bug) and flags
`bold_fullhist_replay.py::run_anchor_validation` as carrying the textually IDENTICAL pattern
(dormant today only because its `ANCHOR_FILLS` list is small/hand-picked) -- follow-up
queued, not fixed this fire (bounded task discipline).

**REVOKE:** `git revert 3d9228d4` (2 files, byte-revertible; the 3 previously-RED tests
would go RED again on revert, which is the expected/correct behavior of a clean revert).

## [2026-08-06T19:25 ET] LANE 4 STRATEGIC ENTRIES: entry-quality ledger + V-d1/V-e3 shadow counter shipped; R-S8 killed -- REVOKE surface

**What shipped (measurement only -- zero trading-path changes):**
`setup/scripts/entry_quality_ledger.py` (standing 6-factor entry-quality ledger + frozen
admissibility battery, prereg `entry-quality-admissibility-prereg-2026-08-06.json` @
**6d6bf8c8** committed BEFORE the runner) and `setup/scripts/entry_shadow_counter.py`
(V-d1 + V-e3 would_block tally per entry, idempotent, folded into the existing
`Gamma_WinnerAutopsy` 16:25 ET fire -- no new scheduled task, fail-open). **Proven in
situ:** full winner_autopsy fire ran tonight and printed `[entry-shadow] 4 tally rows ...
vd1 blocks 0, ve3 blocks 0` -> `analysis/entry-quality/shadow-tally.jsonl` +
`shadow-summary.json` (forward session #1 of 10 logged; neither rule would have touched
winning Thursday).
**Battery verdicts (235 engine entry fills / 26 days, BH across 5 cells):** the lane's
named rule **"require ANY structure event within 8 bars" (R-S8-5m) is KILLED** by its own
pre-committed criterion: delta **-$524**, blocks $3,696 of winners, worst day -$1,760 =
2026-08-04 (it would have gutted the record Tuesday). Structure-PRESENCE survives instead:
R-PRES-1m (=V-e3) +$2,211, **$0 winners blocked**, blocked-WR 0.0%, worst day +$27, G1-G6
pass -- but BH q=0.37 fails the 0.10 bar, so it stays SHADOW (no new prereg needed; its
forward prereg + tonight's counter ARE the next step). V-d1 re-scored: exact reproduction
(+$1,242, 1 winner blocked, q=0.37) -- SHADOW per its frozen prereg.
**Two corrections to standing numbers:** (1) the 08-05 ENTRIES study's population silently
DROPPED an engine entry whose exit was manual-attributed (06-26 safe-2 732P, -$237): true
<=08-05 net is **+$80, not +$317**. (2) V-e3's advertised in-sample basis (n=41, p=0.063)
does NOT reproduce on verifiably-complete SIP bars (26/26 days x 390 RTH 1m bars checked):
true n=28, p=0.29. The 08-05-day subset reproduces exactly, so the prior 1m context was
thin on other days. Forward gates unaffected (they judge forward data only).
**Guards:** `backtest/tests/test_entry_shadow_counter.py` 14/14 green; RED-proofed twice
(V-d1 comparison inverted -> 6 RED; V-e3 quorum 20->0 -> 1 RED), both restored
byte-identical (sha256 225f2a0d...) and re-proven green.
**REVOKE (one line each):** delete the `entry_shadow` try-block in
`setup/scripts/winner_autopsy.py` main() (kills the nightly tally; artifacts inert) / git
revert of the ship commit (removes ledger + counter + guards).

---

## [2026-08-06T19:20 ET] LANE 5 DON'T-TRADE-CHOP: admissibility battery (12 cells) + CHOP EXPOSURE METER shipped -- REVOKE surface

**What shipped (measurement only -- zero trading-path changes):** `Gamma_ChopMeter` 16:08 ET
daily -> `setup/scripts/chop_exposure_meter.py` -> `automation/state/chop-exposure-{date}.json`
+ `-last.json`, rendered as one line in firm-brief.md (`firm_brief.render_chop_lines`,
additive + fail-open). Columns: entries | ord>=4 (CAP-3 forward-clock recorder) | against
V-d1 | zero-structure (CONTEXT, not an alarm) | rr<0.70 | worst consec-loss run (CONSEC4
recorder) | fleet-POOLED REALIZED intraday floor + BRK600 would-trip (the forward-evidence
surface the live equity-based daily_loss_guard.py does NOT have). Prereg frozen BEFORE any
runner: `analysis/recommendations/chop-defense-prereg-2026-08-06.json` @ **5737488a**.
**First real line (tonight):** `CHOP METER 2026-08-06: 4 entries | ord>=4: 0 | against
V-d1: 0 | zero-structure: 0 | rr<0.70: 1 | worst consec-loss run: 1 (contract 1) | fleet
realized: day +1465, floor +0, BRK600 would-trip: no` -- reconciles to broker truth to the
dollar.
**Battery verdicts (208 real fills / 26 dates, trust gate 6/6 PASS; popB = 391-day replay):**
the day-level chop classifier stays DEAD; of 12 fresh per-trade cells, ONE cleared all 8
gates on both populations: **B-RR-070** (range < 0.70x 20-day median at entry: +$765 pop-A,
0 days harmed, blocked-WR 11.4%; **+$1,645 pop-B across 22 helped / 2 harmed days**) -- BH
q=0.50 fails the 0.10 evidence bar, so it is PREREG-with-forward-clock, NOT a ship.
C-NOEVT (block zero-structure entries) is REJECTED at -$2,091 Tuesday; C-AGAINST confirmed
graveyard-adjacent REJECT (-$1,501 Thursday); A-CONSEC-CONTRACT-3 passes gates but is
CAP-3-redundant (identical Wednesday block set, +$653). Full table:
`analysis/deep-research/CHOP-DEFENSE-2026-08-06.md` + `.json`.
**Guards:** `backtest/tests/test_chop_exposure_meter.py` 8/8 green; RED-proofed twice
(meter ORD_ALARM mutation -> 4 RED; firm_brief section removal -> 1 RED), both restored
byte-identical (sha256 e70c1c30... / 3a3a5f9c...) and re-proven green.
**Task verified through the real chain:** State=Ready, MSFT_TaskDailyTrigger, NextRun
08-07 16:08 ET, manual Start-ScheduledTask fire -> LastTaskResult=0, artifact rewritten.
**REVOKE (one line each):** `Unregister-ScheduledTask Gamma_ChopMeter -Confirm:$false`
(kills the nightly fire; brief line degrades to "meter has not run yet", fail-open) / git
revert of the ship commit (removes meter + brief hunk + guards).

---

## [2026-08-06T19:15 ET] LANE-7 MONDAY-READINESS: TV watchdog argv fix PROVEN live + hidden pipeline-hang fixed -- REVOKE surface

**Owed proof delivered (the 2026-08-05 argv fix had shipped UNPROVEN):** staged the real
failure (TV up since 16:27 ET with CDP dead 8,462s), ran the REAL watchdog path -- the
`-Kill` relaunch executed launch_tv_debug.ps1 for real (pre-fix: not a single line ran)
and CDP healed on :9222 (`tv_health_check`: cdp_connected=true, BATS:SPY @5m).

**NEW defect found + fixed during the proof:** `Invoke-TvLaunchSafe`'s
`& powershell.exe $psArgs 2>&1 | Out-File` pipeline BLOCKED until TradingView itself
exited -- launch_tv_debug.ps1 starts TV via Process.Start/UseShellExecute=$false with no
redirection, so TV INHERITS the child's stdout handle and the pipeline never completes.
Masked pre-argv-fix (child died instantly); live repro tonight: tick hung 12+ min past a
successful heal; production `Gamma_TvWatchdog` (ExecutionTimeLimit=PT4M) would be KILLED
before `Test-CdpReady`/healed-logging ran -- the 2026-07-31 `*_FAILED` escalation was
unreachable in exactly the scenario it was built for.
**Fix:** Start-Process + sidecar-file redirection + `Wait-Process` on the CHILD only;
`CdpTimeoutSec` default 12->90 (measured cold boot-to-CDP >29s; 12s poll flags every real
heal as FAILED). **End-to-end proof:** killed TV, real `run-tv-watchdog.ps1` completed in
**67s** with `tv_action: relaunch_fresh_healed` written same-tick
(tv-watchdog-status.json 2026-08-06T23:09:30Z).
**Guard:** `backtest/tests/test_tv_launch_argv_2026_08_05.py` (5 tests -- the file the
argv fix CITED but never wrote, L249 class) + existing suite, 12/12 green. RED-proofed by
3 source mutations (argv splat back / blocking pipe back / timeout 12): 2+2+1 guard
failures, restored byte-identical (sha256 7ca02ee1...), green re-run.
**Revert (one line each):** restore the `& powershell.exe $psArgs 2>&1 | Out-File` block
in `_shared.ps1#Invoke-TvLaunchSafe` (git revert of this commit) / set CdpTimeoutSec 90->12.

---

## [2026-08-06T16:15:04 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-06 -- 5 GREEN / 0 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 113 tick(s) showed in_trade>0. 11 real fill(s) dated 2026-08-06: safe-2@10:31, safe-2@10:32, risky-1@10:32, risky-3@10:32, bold-2@10:32, safe-2@10:33, bold-2@10:34, safe-2@10:34, bold-2@10:34, safe-2@10:35, safe-2@14:21. Field-level populatio… |
| WS6 regime stamp | GREEN | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-08-06, generated_at_et=2026-08-06T08:40:03-04:00 (hhmm=08:40, in 08:15-08:40 window=True). today-bias.json date=2026-08-06, regime_context.stamp_date=2026-08-06 (present=True, dates_match=True). one_liner='Yesterday 2026-08-05 (Wed) = gap-fade (range 0.95%, gap +0.60%, c… |
| WS3 level hysteresis | GREEN | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 51 distinct near-price levels. Worst: 769.80 flipped 5x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 171 level-refresh run(s) logged (171 ok), hysteresis_held fired 36 time(s) across 2 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-06 window_end=2026-08-05 (baseline window_end=2026-07-31, advanced=True). bear now: RED n=11 (delta +1 vs baseline n=10) exp=$-78.55/tr, verdict_moved=False. bull now: UNDERPOWERED n=8 exp=$105.75/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-08-06T16:00:03 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2', 'risky-3']. 268 theta-clock row(s) dated 2026-08-06 across 2 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=268, unavailable=0. sti… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-06 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-06`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## [2026-08-06T05:41 ET] conductor: OK -- SCOUT-PREMARKET-BUDGET-CHRONIC-FAIL -- commit `8ad0b364`

Budget gate PASSED ($5.06/$30, 1/4 fires pre-fire). Engine health GREEN, market closed
(05:30 ET). STAGE-1 priority-1 (fill-funnel/self-check) surfaced a NEW, TODAY-dated
self_check DEGRADED finding riding the same RUN-PS1-HIDDEN masked-exit visibility fix two
prior fires shipped (2026-08-04/05/06): `run-scout-premarket.ps1 (exit=[1], 1x)`.
**Root cause named in one sentence:** `-MaxBudgetUsd 0.50` (unchanged since the script's
2026-06-15 creation) was always too tight for a WebSearch-driven macro/news scan, and the
underlying `claude` CLI's `Error: Exceeded USD budget (0.5)` -> exit=1 has fired on EVERY
dated log checked back to 2026-07-20 (11 sample dates, 11/11 failures) -- ~7-8 weeks of
100% daily failure, invisible to Task Scheduler's `LastTaskResult` via the vbs launcher's
fire-and-forget hop, only now surfaced by the masked-exit detector shipped the last 2 fires.
**Live impact confirmed, not assumed:** `automation/scout/state/scout_output.json` (which
Premarket at 08:30 ET reads for macro/news bias context) is stuck on its 2026-08-04
`status: "partial"` content -- 2 consecutive sessions (08-05, 08-06) with zero fresh write.
**Fix:** raised to `-MaxBudgetUsd 1.00` (still 2nd-cheapest premarket-class task on the
roster; siblings doing similar work: futures-premarket $2.00, premarket itself $3.00).
**Guard + RED-proofed live:** `backtest/tests/test_scout_premarket_budget.py` (2 tests,
pins the exact broken 0.50 value + a 1.00 floor) -- reverted the REAL file to 0.50 by hand,
confirmed both assertions fail with the exact evidence string quoted in the failure message,
restored to 1.00, re-confirmed 2/2 green. Full curated pair + `test_conductor_budget.py`
18/18 green (zero regressions).
Rail-4 N/A (infra/scheduling wrapper edit, zero params/heartbeat_core/filters/placement/
exit-code touched -- Scout feeds descriptive premarket context, never a live entry input).
**REVOKE:** `git revert 8ad0b364` (2 files modified, 2 new files added -- clean revert).
Filed `strategy/candidates/_lesson-inbox/budget-cap-misized-at-birth-invisible-for-8-weeks-2026-08-06.md`
for lesson-author (new angle on the C7/C14 class: a budget knob can be ENFORCED correctly
and still be silently wrong because the VALUE was mis-sized at birth, not drifted). Filed
`BUDGET-ROSTER-AUDIT-MAXBUDGETUSD` (MED, queue.md) as the bounded next-fire follow-up --
audit all `-MaxBudgetUsd` values roster-wide for the same class of outlier; correctly NOT
attempted this fire (single-item scope).
Committed via `commit_scoped.py` (4 files, pathspec-scoped; confirmed 0 other files left
staged for absorption per L271/C34 discipline).
Autonomy metric refreshed via `conductor_outcome.py` this same fire.

---

## [2026-08-06T01:15 ET] conductor: OK -- VBS-WRAPPER-EXIT-CODE-BLIND-SPOT 2nd half -- self_check now reads run_ps1_hidden.py's exit-code log

Budget gate PASSED ($0/$30 pre-fire). Engine health GREEN, market closed (01:00 ET).
STAGE-1 priority-1 (fill-funnel/self-check) clean (DEGRADED only on expected
PDT-BLOCKED[bold]). `task_scorer.py --top` picked `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT`
(HIGH), advisory said re-verify it still reproduces before acting -- it did, and the
live re-check found the item's OWN prior "PARTIAL, LOW-RISK HALF" fix (2026-08-04/05)
only covered `run_cmd_hidden.py`'s relay (24/108 tasks). Enumerated the fleet live via
`Get-ScheduledTask`: 108 `Gamma_*` tasks route through `run_exe_hidden.vbs`, 84 of them
NOT on that relay -- including `Gamma_EodFlatten`, `Gamma_EodFlatten_Aggressive`,
`Gamma_SightBeacon`. Found those 84 mostly route through a SECOND pre-existing,
already-exit-code-capturing relay (`run_ps1_hidden.py`, dated to a "5/17 evening
foot-gun fix") that nothing had ever consumed.
**Fix:** `self_check.check_run_ps1_hidden_masked_exit()` (sibling of the run_cmd_hidden
check, problem #17), with a parser that reads each exit line standalone (script name is
embedded in the line) rather than sequentially pairing launching/exit lines -- the real
log routinely interleaves 5+ concurrent launches, which would have broken a naive copy
of the sibling's pairing logic.
**LIVE FINDING, evidence only, not fixed this fire:** `run-eod-flatten-aggressive.ps1`
exited 1 on all 3 of the last 3 trading days (08-03/08-04/08-05); `run-eod-flatten.ps1`
and `run-sight-beacon.ps1` each exited 1 once on 08-05 -- all previously invisible.
Cross-checked against `Gamma_EodFlattenCore` (deterministic, both accounts, fires ~3min
before the LLM path, `LastTaskResult=0` every date) and `engine-health.json`'s
`position_safe`/`position_bold` (GREEN flat every date) -- **confirmed backstopped, not
a realized safety incident.** Root cause of the LLM prompt's exit=1 NOT investigated
blind (OP-0) -- filed `EOD-FLATTEN-LLM-PROMPT-EXIT1` (MED) for the next fire.
**Verified, not just tested:** 13 new guard tests, RED-proofed via rename-and-restore
(L238 -- explicitly avoided `git stash`, which on this repo picks up ~1800 live-daemon
state-file diffs; git-showed the pre-edit HEAD into place, confirmed 12/12 correctly
fail, restored, re-confirmed 12/12 green), full self_check-tagged suite 132/132 green
(zero regressions), one test runs against the REAL 2026-08-05 on-disk log (not a
synthetic fixture) and asserts the exact 3-script finding.
Zero vbs edits, zero scheduled-task edits, zero live-trading-path touch -- purely
additive read of a log that already existed (rail-4 N/A, infra visibility only).
**REVOKE:** `git revert <this commit>` (2 files, additive-only).
Next fire: the CORE vbs-synchronous fix still matters for whatever tasks sit on NEITHER
relay (incl. `Gamma_HeartbeatCore` itself -- exact count not re-enumerated this fire) and
stays behind its own `/fable-blast-radius` pass; `EOD-FLATTEN-LLM-PROMPT-EXIT1` (MED) and
`PROSPECTOR-SEMANTIC-DEDUP-GAP` (MED) are the next-ranked queue items.
Autonomy metric refreshed via `conductor_outcome.py` this same fire.

---


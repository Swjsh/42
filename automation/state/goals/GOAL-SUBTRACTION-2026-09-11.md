# GOAL: SUBTRACTION-2026-09-11

> J verbatim (2026-09-11 ~20:20 ET, after three red sessions): *"I fear the project was over
> engineered or something by Opus because he's been rambling a lot lately.. we need a full audit.
> why are we all of a sudden now losing every day and cant play any levels properly"*

Parent: [`analysis/deep-research/FABLE-FULL-AUDIT-2026-09-11.md`](../../../analysis/deep-research/FABLE-FULL-AUDIT-2026-09-11.md)
§3 (over-engineering, measured) and §5. The audit found the losses are the engine's shape on a
compressing tape, not a regression — but it also found the machinery costing money and attention in
specific, fixable places. **This goal is the subtraction pass.** Every item REMOVES a line, a task, a
surface, or a blind spot. Nothing here adds an instrument, a lane, a sidecar, or a report.

## BUILD POSTURE (standing until 2026-10-30, J's words are the mandate)
- **No new instruments, shadow lanes, sidecars, dashboards or reports** until the freeze closes,
  unless one is the ratifying read of a filed prereg. Ask "does this remove a line or add one?"
- This does NOT touch the trading path (config freeze unchanged) and does NOT touch position safety.
- Conflict noted and resolved: OP-25's "empty queue → brainstorm → ship 3+ tasks" posture is
  superseded by J's 09-11 directive for the rest of the window. Revoke: close this goal.

## WHY THESE FIVE AND NOT A GENERAL CLEANUP
Each item is a measured cost from the audit, with the measurement quoted:
1. **195 `Gamma_*` task registrations, 23 enabled.** 145 sit in `quiet-mode-baseline.json` at
   State 3; 158 are on J's 09-05 manual hold ("stop everything immediately (popups)"). Parked
   registrations are attention debt and a restore-time hazard (`quiet-mode-restore.json` re-enables
   whatever is on its list). They are all restorable: 156 `install-*.ps1` scripts exist.
2. **Two silent engine outages in one week** (09-09 last tick 15:06, no alarm; 09-11 97 ERROR
   ticks 12:16–13:04). `Gamma_DeadMansSwitch` (2-min) watches POSITIONS, not ticks. Nothing watches
   "HeartbeatCore stopped ticking during RTH".
3. **Reports that print noise.** The journal's "Engine Misses Today" block scored 54 missed
   setups at **−$839** and called it "0% of available edge captured" — missed setups that LOST money
   are not missed edge.
4. **The 15:55 LLM flattener's harness tree-kills 22–24 processes at 15:57** when `claude --print`
   lingers (09-10: `TIMEOUT after 120s - killing root pid=29652 plus 24 descendants`). The 09-08
   STATUS claim that the flatteners are "dead on every fire" is STALE — both ran exit=0 with useful
   reconcile appends on 09-10 and 09-11 — so the decision is NOT "retire"; it is "what does the kill
   hit?" (UNVERIFIED hypothesis: `MCP_AUDIT_YELLOW mcp_procs=FAIL -- 0 alpaca-mcp-server` at 23:50
   the same night). Retire/keep is decided on THAT evidence.
5. **No history for the premarket bias or the level set.** `today-bias.json` is overwritten daily;
   `journal/key-levels-archive/` stopped 07-02 (`Gamma_LedgerArchive` Disabled). The 10-30
   question "should no-trade days be sat out" (09-11: bias said no-trade and named 756.64 / 757.81 /
   763.7 while the engine traded 5-minute swing pivots) cannot be answered without ≥ 20 archived days.

## DONE-WHEN
Falsifiable, each checked by a command or ledger row quoted in the PROGRESS LOG:
- (a) **Registrations.** `(Get-ScheduledTask | ? TaskName -like 'Gamma_*').Count` drops from 195 to
  ≤ (enabled + restore_to_ready + never_restore + trading-critical held). Only registrations that are
  (i) Disabled ≥ 7 days, (ii) NOT on `quiet-mode-restore.json` / `quiet-mode-never-restore.json`,
  (iii) restorable by a named `install-*.ps1` are unregistered. Dry-run list committed BEFORE the
  delete; `backtest/tests/test_scheduled_tasks_doc.py` green after; STATUS line names the count and
  the restore command. The 23 enabled tasks are never touched.
- (b) **Tick dead-man.** `Gamma_DeadMansSwitch` (existing task, no new task) also raises a STATUS
  `## Known broken` line when, during 09:35–15:55 ET on a trading day, `core-decisions-tick.json`
  is older than 5 minutes. RED-proofed by a test that feeds it a stale marker. Re-check on the
  09-09 replay: it would have fired at 15:11.
- (c) **Misses block.** The journal's "Engine Misses" section either prints net positive missed
  P&L only, or prints "no positive missed edge" — it can no longer report a negative dollar figure
  as missed edge. Guard test added; 09-10's journal regenerates without the false line.
- (d) **Flattener kill decision.** The `_shared.ps1` timeout kill logs IMAGE NAME + command line
  for every pid it kills (one line each). After ≥ 2 sessions of evidence: if the kill hits
  `alpaca-mcp-server` / Core processes → the LLM flatteners are retired (Disable, not delete;
  revoke = Enable-ScheduledTask) and `mcp_procs=FAIL` is checked the following night; if it hits
  only their own children → keep, close the item, correct the 09-08 STATUS line.
- (e) **Archives.** `journal/bias-archive/<date>.json` and `journal/key-levels-archive/key-levels-<date>.json`
  exist for 3 consecutive sessions, written by an EXISTING fire (the premarket fallback or
  `Gamma_Home`), not a new task.

## QUEUE
- [x] (a) dry-run the registration map: table of every Disabled `Gamma_*` task with held-since, restore-list membership, install script → commit `analysis/audits/task-registrations-2026-09-1x.md`; then unregister the eligible set; run the registry test; STATUS line.
- [x] (b) tick dead-man inside `dead_mans_switch.py` + RED-proofed test + 09-09 replay check.
- [x] (c) Misses block: find the producer (`journal` EOD writer), fix the sign handling, guard test, regenerate 09-10.
- [ ] (d) `_shared.ps1` kill logging (image + cmdline per pid), then the keep/retire decision after ≥ 2 sessions of kill logs.
- [ ] (e) bias + key-levels archive lines inside an existing daily fire; re-check after 3 sessions.

## PROGRESS LOG
- 2026-09-11 20:5x ET (Fable, audit session): goal authored. Done same night, outside this queue:
  freeze scope extended to the four level producers (`setup/hooks/doctrine.py` FROZEN_TRADING_PATH
  + hook test), audit + prereg + instrument committed (`df9412de`, `f9370c2d`), STATUS lines, memory.
  The "retire the LLM flatteners" recommendation from the audit's §5 was WITHDRAWN on fresh
  evidence (both ran exit=0 on 09-10 and 09-11) — replaced by item (d).
- 2026-09-11 20:49 ET — opened by goal_autopilot
- 2026-09-11 22:5x ET (Fable, continuation 1/3): **(a) DONE.** Map first (`analysis/audits/task-registrations-2026-09-11.md`, commit `a38f2138`): 195 = 23 ESSENTIAL + 135 nightly-blackout + 37 parked -- the goal's own premise ('172 parked') corrected. Unregistered 6 (FuturesEod dup, Grind_Vwap, Drive, ConductorRTH, MultiCore, TwinChaos): count 195 -> 189 (Ready 23 / Disabled 166), `test_scheduled_tasks_doc.py` 5 passed, registry section `## Unregistered 2026-09-11` added with restore commands. HELD Gamma_DailyReview for (e): `run-daily-review.ps1` is the key-levels-archive writer (stopped 07-02 = its last run). 30 parked stay (no install script / ESSENTIAL / restore-listed / started by name). Revoke = the install script per row.
- 2026-09-11 23:38 ET (Fable): J's follow-up directives superseded the queue order -- MOST-TOUCHED level cap shipped (22 -> 6 lines, STATUS line) and `GOAL-SD-LIQUIDITY-ZONES-2026-09-11` authored; this goal is RE-QUEUED right behind it (items (b)-(e) still open, (a) done). Item (e) note: `run-daily-review.ps1` is the key-levels archiver.
- 2026-09-12 01:19 ET — opened by goal_autopilot
- 2026-09-13 08:2x ET (conductor AFTERHOURS): **(b) DONE.** `check_tick_deadman()` added to
  `dead_mans_switch.py` -- reads the shared `core-decisions-tick.json` marker (written every
  core tick by `heartbeat_core._write_tick_marker`, both accounts) during 09:35-15:55 ET on a
  weekday, raises a de-duplicating `status_known_broken.upsert()` '## Known broken' line past
  5 minutes stale, clears itself once fresh/outside the window. Runs unconditionally every
  fire (own gating, independent of the per-arm position checks and their wider 09:32-15:58
  window). Wired into both the "outside_rth" snapshot and the normal report as
  `report["tick_deadman"]`. Picked because item (5)'s NOT-BEFORE 09-17 clock and item (1)'s
  Monday-only DONE-WHEN left the active goal (GOAL-EARN-YOUR-KEEP) with no pickable item this
  fire -- the goal's own operating rule says take this item "the moment this goal has no open
  item".
  **09-09 replay (DONE-WHEN's own re-check):** new test pins the exact incident numbers --
  last tick `2026-09-09T15:06:14`; at 15:10:00 (3m46s later) `stale=False`; at 15:11:15
  (5m1s later) `stale=True, action=FLAGGED` -- would have fired 44 minutes before the 50-min
  gap was ever surfaced anywhere.
  **RED-proofed live:** temporarily forced `stale = False` in `check_tick_deadman` -- 4 of the
  10 new tests failed exactly as expected (`test_check_tick_deadman_flags_stale_marker_during_window`,
  `..._replay_2026_09_09_fires_at_1511`, `..._clears_when_fresh_again`,
  `test_main_wires_tick_deadman_into_the_report`) -- reverted, 23/23 green again.
  **Verified, quoted:** `pytest backtest/tests/test_dead_mans_switch_2026_09_01.py -q` ->
  23 passed. Filtered sweep `-k "dead_mans or status_known_broken or known_broken"` -> 77
  passed, 0 pre-existing regressions. `doctrine.frozen_path_hit()` -> None on both touched
  files (neither is on `FROZEN_TRADING_PATH` -- this is a pure safety-monitoring addition,
  no `GAMMA_FREEZE_OVERRIDE` needed). Curated pre-commit safety gate: 59 passed. Commit
  `4a5484b9` (2 files, 286 insertions, 0 deletions -- additive only, no existing function's
  behavior changed).
  **Rail:** guard = the 10 new RED-proofed tests + 59/59 curated safety gate (a); revert =
  `git revert 4a5484b9` (b); this entry is the REVOKE report (c).
  **Note for item (e)/(c)/(d):** still open, not picked up this fire (scope discipline --
  one bounded item per conductor fire).

- 2026-09-13 08:5x ET (conductor AFTERHOURS, continuation -- Stop hook rejected an open-ended
  "next fire" ending, correctly: not a genuine fork, OP-0 says act): **(c) DONE.**
  `missed_setups_section.py::render_section` computed its headline from the scanner's raw
  NET sum (winners + losers), so a day with 51 losers and 3 winners printed e.g. "-$839 paper
  P&L left on the table" -- a net LOSS framed as forgone profit. Fix: headline now sums ONLY
  winning rows; if that sum is <=0 it prints "no positive missed edge" (net figure still
  shown as CONTEXT, never framed as "left on the table"); if >0 it shows the winners-only
  figure with a "(before N would-be loser(s) worth $X)" note. `total_pnl` /
  `edge_capture_pct` (JSON fields) unchanged -- formatter-only fix.
  **Regenerated 09-10:** `analysis/eod-deep-2026-09-10.json`'s archived
  `research_handoffs.missed_setups_scan` (the ORIGINAL 54-setup/-$838.52 scan, not a re-scan
  against today's drifted key-levels.json) re-rendered through the fixed formatter and
  spliced into `journal/2026-09-10.md` in place of the old section -- new headline:
  "54 missed setups, +$548 of positive P&L left on the table (before 34 would-be loser(s)
  worth $1,386)". journal/*.md is untracked by git (state, not source) -- no commit needed
  for that half.
  **RED-proofed live:** forced the `positive_pnl<=0` branch unreachable -- 1 of 6 new tests
  failed exactly as expected, reverted, 6/6 green.
  **Verified, quoted:** `pytest backtest/tests/test_missed_setups_section_sign_fix_2026_09_13.py -q`
  -> 6 passed. Filtered sweep `-k "missed_setups or eod_quant_guard or eod_deep"` -> 31
  passed, 0 regressions. `doctrine.frozen_path_hit()` -> None on both touched files (no
  override needed). Commit `58d8821a` (2 files, +186/-6).
  **Rail:** guard = 6 new RED-proofed tests + 31/31 filtered sweep (a); revert =
  `git revert 58d8821a` (the journal file itself is untracked state, so a code revert alone
  leaves that day's corrected text in place -- acceptable, it is a factual correction not a
  behavior change) (b); this entry is the REVOKE report (c). Items (d)/(e) still open.

- 2026-09-13 10:0x ET (conductor WEEKEND): **(d) logging half DONE**, decision half still
  open (needs >=2 sessions of live kill evidence per the item's own DONE-WHEN, not
  applicable yet -- the flattener hasn't timed out since this shipped). GOAL-EARN-YOUR-KEEP
  (the ladder's active goal) had no pickable item this fire: item (1) is `[~]` waiting on
  Monday's live risky-3 ledger, item (5) is NOT-BEFORE 09-17 -- per that goal's own operating
  rule ("the conductor should take it [GOAL-SUBTRACTION] the moment this goal has no open
  item"), took this item.
  Shipped `Get-ProcessKillInfo` in `_shared.ps1` (new helper, read-only, CIM-backed) +
  wired it into the `Invoke-Claude` timeout-kill branch: before `Stop-ProcessTree` removes
  the subtree, every pid's Name + CommandLine is captured and logged one line each
  (`KILL_TARGET pid=... image=... cmdline=...`) via the existing `Write-TaskLog` -- no new
  report/file, per the goal's build posture. CIM data disappears once a process is gone,
  so this has to run BEFORE the kill, not after (a bare pid list was already logged after
  the kill; this adds the image+cmdline WHILE the pids are still alive).
  **$0 regression guard** (`test-kill-logging.ps1`, no `claude.exe` spawn, no Anthropic
  tokens -- deliberately avoided `test-timeout.ps1`'s pattern of spending real tokens for a
  smoke test): spawns a real `powershell.exe` child, asserts `Get-ProcessKillInfo` correctly
  attributes its pid/Name/CommandLine and skips a pid that doesn't exist (no null-padded
  rows). **RED-proofed live**: broke `Name` capture to a literal `"REDPROOF_BROKEN"` ->
  1 of 4 assertions failed exactly as expected (`Name captured as powershell.exe`) ->
  reverted -> 4/4 green again. Quoted: `PASS: returns exactly 1 row ... PASS: attributed
  row's Pid matches ... PASS: Name captured as powershell.exe ... PASS: CommandLine
  captured the real command line ... ALL PASS`.
  `doctrine.frozen_path_hit()` -> `None` on both touched files (`_shared.ps1`,
  `test-kill-logging.ps1`) -- no `GAMMA_FREEZE_OVERRIDE` needed, pure safety-monitoring
  addition. Curated pre-commit safety gate: 59/59 passed. Commit `6486d77a` (2 files,
  +84/-0, additive only -- the pre-existing "killed pids: ..." summary line is unchanged).
  **Rail:** guard = the 4-assertion RED-proofed script + 59/59 curated gate (a); revert =
  `git revert 6486d77a` (b); this entry is the REVOKE report (c).
  **Decision half not yet reachable**: needs the flattener to actually timeout-kill in
  >=2 live sessions post-ship before the keep/retire call can be made on evidence, per the
  item's own text. Next conductor fire that finds a `KILL_TARGET` line in a task log should
  read who it names and progress the decision. Item (e) still fully open.

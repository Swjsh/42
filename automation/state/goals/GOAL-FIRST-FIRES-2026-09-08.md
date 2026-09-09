# GOAL: FIRST-FIRES-2026-09-08

> Queued by Fable 2026-09-05 08:14 ET for the first trading day after the weekend build (Tue 2026-09-08; Mon is
> Labor Day). Four new scheduled instruments and one restart rule shipped this weekend and have never
> fired on a live session: Gamma_ZeroEnterAutopsy (16:10 ET), Gamma_RightTailCapture (16:20 ET),
> Gamma_CheckpointPacket (23:30 ET), Gamma_VixBullHardCapUnblockShadow (16:57 ET), and the Kitchen
> keepalive restart-when-idle. Lesson C7: rc=0 from a hidden-chain task is never evidence -- the
> output stamp is. This goal is the evidence.

## DONE-WHEN
After Tuesday's session: each of the four tasks has (a) a run-cmd/run-ps1 hidden log `exit=0` line
dated 2026-09-08 within 3 min of its slot, (b) a fresh output file dated 2026-09-08 (analysis/zero-
enter/ZERO-ENTER-2026-09-08.json or the day's "no zero-enter day" marker; analysis/right-tail/
CAPTURE-2026-09-08.json + ledger row; markdown/planning/CHECKPOINT-2026-09-29.md regenerated with a
09-08 stamp; the VIX-bull shadow ledger row), (c) sane content (the capture file scores Tuesday's real
waves; the packet's verdict counts match the inventory); the Kitchen daemon shows a restart on the
new code (pid change in the keepalive log with reason "idle + stale code", a kitchen-stage1-run-log
row after the restart); the tickers lane's Gamma_TickersDayCheck open/eod files for 09-08 exist with
0 TICK_ERROR; the 09:51-style RTH gap check (`rth_tick_gaps`) reads GREEN for 09-08 or names the gap.
Any miss is filed to STATUS Known broken with the exact failing node and fixed the same fire if the
fix is off the trading path.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: verification and reads only; no trading-path edits.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Every stamp is read from `python setup/scripts/et_clock.py` in the same call, never typed.
- Not before its date: items are gated on real fires having happened; an early fire records "not yet" and stops.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] V1 -- (after 16:30 ET 09-08) zero-enter + right-tail + tickers day-check + rth_tick_gaps evidence, quoted. DONE 2026-09-09 00:xx ET, see PROGRESS LOG.
- [x] V2 -- (after 17:05 ET 09-08) VIX-bull shadow row + Kitchen daemon restart evidence, quoted. DONE 2026-09-09 01:xx ET, see PROGRESS LOG.
- [ ] V3 -- (after 23:35 ET 09-08) checkpoint packet regenerated with the 09-08 stamp; verdict counts
  vs inventory; cockpit tile numbers match the files (DOM read).
- [ ] V4 -- Any miss -> Known broken line + fix (off-path) or prereg; PROGRESS LOG with every quoted stamp.

## J-DECISIONS
- None.

## PROGRESS LOG
- {now} ET -- queued by Fable (EOD-audit session) for the Tuesday conductor.
- 2026-09-05 08:14 ET — opened by goal_autopilot
- 2026-09-05 11:55 ET -- deferred back to queued by Fable: the ladder now carries not_before:2026-09-08, so the autopilot opens this on Tuesday, not on a Saturday fire that can only say "not yet".
- 2026-09-09 00:25 ET — opened by goal_autopilot
- 2026-09-09 00:xx ET (Stop-hook continuation 1/3): V1 DONE. **Zero-enter** (Gamma_ZeroEnterAutopsy 16:10 ET): hidden log `zero_enter_autopsy.py [pid=34528] launching 2026-09-08 14:10:00` -> `exit=0 [pid=34528] 2026-09-08 14:10:03` (3s, local MT = 16:10 ET). Output `analysis/zero-enter/ZERO-ENTER-2026-09-08.json` dated 09-08, 77 bars, real content. Content caveat found and root-caused (NOT fixed -- correctly declined, see below): `day_summary.grade="regressing"`/`grade_reason` says "(0 enters, 772 RTH ticks)" even though core-decisions.jsonl shows 23 raw ENTER-verdict rows (2 PLACED) that day -- looked like a bug (`run_autopsy()` calls `co._grade_zero_enter_day(day)` unconditionally, and that function's reason string hardcodes the literal text "0 enters" as decorative prose, not a computed check). Investigated whether to gate the call on a real zero-enter precondition, but found the SAME "high raw-ENTER-count + regressing grade" pattern on the hand-validated Z2 fixture day (2026-09-02: 25 raw ENTER rows, 4 PLACED, still asserted grade="regressing" by the existing pinned test `test_grade_matches_conductor_outcome`) -- so a real_enters-based gate would have broken the existing hand-validated ground truth, meaning I cannot state a one-sentence root cause I'm confident acting on. Per debugging discipline (no band-aid without a stated mechanism), declined to ship a guess; filed as an open question, not a fix.
  **Right-tail** (Gamma_RightTailCapture 16:20 ET): hidden log `right_tail_capture.py [pid=33492] launching 2026-09-08 14:20:00` -> `exit=0 [pid=33492] 2026-09-08 14:20:08` (8s). `analysis/right-tail/CAPTURE-2026-09-08.json` dated 09-08, 3 waves found (all bear, `computed=false` -- "no OPRA option cache" for same-day 0DTE symbols, a known/disclosed data-timing gap, not a new defect). `ledger.jsonl` carries 3 rows dated 2026-09-08 (bold-2/safe-3/risky-1, all "no first wave taken this arm/day").
  **Tickers day-check** -- REAL MISS FOUND AND FIXED. `automation/state/tickers/day-check-2026-09-08-open.json` exists (09:40 ET open phase, matches the per-arm GOAL-TICKERS-LANE-2026-09-04.md PROGRESS LOG line: all 3 arms GREEN). But NO `day-check-2026-09-08-eod.json` and the 09-08 hidden-log has exactly ONE `tickers_day_check.py` launch all day (07:40 MT only) -- the 15:05 ET eod-phase check never fired. Root cause, verified live: `Export-ScheduledTask -TaskName Gamma_TickersDayCheck` showed **1 CalendarTrigger** (07:40 MT only), while `setup/scripts/install-tickers-day-check.ps1` (current HEAD, unchanged since its `ef562fae` authoring commit) defines BOTH `$tOpen` (07:40) and `$tEod` (13:05) and passes `-Trigger @($tOpen, $tEod)` with its own built-in self-check (`if ($t.Triggers.Count -ne 2) { exit 1 }`) -- the live registration had silently regressed to 1 trigger (plausibly during one of the two later "silence sweep" re-registration passes, `60950dc3`/`cf213c39`, though the exact mechanism wasn't traced further -- out of this bounded item's scope). **FIXED:** re-ran the idempotent install script -- `OK: Registered Gamma_TickersDayCheck State=Ready Triggers=2 NextRun=09/09/2026 07:40:00`. Independently re-verified via `Export-ScheduledTask`: both CalendarTriggers now present (07:40 + 13:05 MT). Per-arm day files (`tickers-N/day-2026-09-08.json`) confirm the LANE itself traded fine regardless (3 arms, 3 real fill round-trips, all flattened by `tickers_flatten` -- the miss was in the OBSERVABILITY instrument, not the trading path). Zero files touched other than the Task Scheduler registration -- no code diff, nothing to RED-proof/revert; guard = the install script's own trigger-count assertion (already proven to catch this class) + `unattended_health.py`-style periodic monitoring is a small LOW follow-up, not built this pass (budget).
  **rth_tick_gaps**: already quoted earlier this session (engine-health.json, checked at 00:00:01 ET) -- `"rth_tick_gaps","status":"GREEN","detail":"no RTH gap >3m on safe (2026-09-08)"`.
  `conductor_outcome.py record` called for this continuation.
- 2026-09-09 01:xx ET (conductor AFTERHOURS fire): V2 DONE. **VIX-bull shadow** (`Gamma_VixBullHardCapUnblockShadow`, 16:57 ET + self-heal repeats at 17:12/17:27 ET): `run-py-venv-hidden-2026-09-08.log` -- `[2026-09-08 14:57:02] vix_bull_hard_cap_unblock_shadow.py exit=0`, `[2026-09-08 15:12:02] ... exit=0`, `[2026-09-08 15:27:03] ... exit=0` (local MT, = 16:57/17:12/17:27 ET). `analysis/recommendations/vix-bull-hard-cap-unblock-shadow-summary.json` regenerated at `_generated_at_et: 2026-09-08T17:27:02` (matches the last self-heal fire) -- `n_band_entries_seen=0`, `n_matched_round_trips=0`, `status=ACCRUING`: no safe-2 bull entries landed with VIX in [18,22) that day, a legitimate empty result (not a bug) since the ledger file is correspondingly 0 bytes -- deterministic full-rewrite, no stale carryover.
  **Kitchen daemon restart** -- pid DID change (30664 -> 5396) but via a DIFFERENT mechanism than the goal text's literal "idle + stale code" phrasing: `supervisor-keepalive-2026-09-08.log` shows `kitchen_daemon: DEAD (pid file names 30664 but that pid is not the daemon (or is gone)) -- relaunching` / `relaunched pid=5396 (launched)` at 21:06:44/46 local, alongside simultaneous DEAD+relaunch of `companion`, `dashboard`, `discord_bridge` -- a box-reboot signature, not the idle-recycle policy (`supervisor_keepalive.py`'s actual string is `idle+stale-code`, which never appears in today's log; confirmed via `grep`). Root-caused via `Get-WinEvent`: system-initiated reboot (`Kernel-Power` Id=109, "Action: Power Action Reboot, Reason: Kernel API") at 17:20:19 local, session unlocked 17:22:41 local -- but the supervisor task itself then sat dark until 21:06:41 (3h44m post-unlock, `NumberOfMissedRuns=0` despite the gap). Filed as `SUPERVISOR-KEEPALIVE-REBOOT-RESUME-GAP-2026-09-08` (MED) in queue.md -- not trading-path (19:20-23:06 ET, after the 15:55 flatten; `Gamma_HeartbeatCore`/`Gamma_SightBeacon` have independent RTH triggers, confirmed no `rth_tick_gaps` RED). Post-restart liveness confirmed: `kitchen-status.json` `recent_completed_top_10` shows continuous task completions resuming within ~1 min of the 21:06:46 relaunch (e.g. `833bd020` completed `2026-09-08T21:47:46+00:00` = 15:47 local) through to the newest entry `2026-09-09T03:07:14+00:00` (21:07 local) -- daemon fully recovered, not stuck. `kitchen-stage1-run-log.jsonl` (a narrower Stage-1-specific log, distinct from the general completion feed above) has no rows after 15:47:29 local pre-restart -- consistent with it just not being the log channel this daemon's post-restart work happened to hit yet, not a stall (the broader `kitchen-status.json` feed is the stronger liveness signal and is unambiguous).
  `conductor_outcome.py record` called for this fire.
## HONEST STATE
V1 done (evidence quoted, 1 real infra miss found+fixed, 1 content oddity investigated+declined-to-guess). V2 done (evidence quoted for both halves; found + filed a genuine new MED infra lead -- reboot-to-supervisor-resume gap -- rather than silently accepting the literal "idle+stale-code" wording that didn't match what actually happened). Not fixed this pass: the zero-enter grading wording question (still open, filed under V1 for a future fire) and the new reboot-resume-gap mechanism (filed to queue.md, needs a wider Get-WinEvent ID sweep before guessing a fix). V3 (checkpoint packet) still open.

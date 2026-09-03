# queue.md consolidation archive -- 2026-09-03

Extracted verbatim from `automation/overnight/queue.md` when it crossed the 450,000-byte retention cap enforced by
`backtest/tests/test_queue_md_retention_cap.py` (OP-22: "every append-only producer has a retention cap;
hitting it triggers CONSOLIDATION"). Same archival rule as prior consolidations: every item whose checkbox is
`[x]` AND whose terminal status resolves to done/closed/resolved/cancelled/decided/shipped, or whose head line
names CLOSED/DONE/SHIPPED/RESOLVED with a date.

Items archived: 4  (17,271 bytes)

Verified before extraction: no still-open item's `depends:` references any archived id (checked against the
full open set, not a sample). Nothing was deleted -- every item below is byte-identical (LF-normalised) to
what left the live file.

---

- [x] CONDUCTOR-2030-FIRE-VS-QUIET-MODE (LOW) :: quiet_mode.py's weekday 18:00-23:00 blackout disables Gamma_Conductor (not in ESSENTIAL), so the documented 20:30 ET AFTERHOURS fire never happens (STATUS shows zero fires 18:00-23:59 ET). Either add Gamma_Conductor to ESSENTIAL or fix conductor.md's '3 fires/night' claim. :: depends:none :: status:pending
  **CLOSED 2026-09-03 00:50 ET (Fable close-out pass):** DONE 2026-09-02 (work order §2d): `Gamma_Conductor` triggers verified live 2026-09-03 00:45 ET = 22:10 / 23:00 / 03:30 MT (00:10 / 01:00 / 05:30 ET), all outside the 18:00-23:00 ET quiet window. :: status:done
- [x] QUOTE-TAPE-HAS-NEVER-CAPTURED-A-SESSION (HIGH, instrument-dead, filed 2026-08-29 from the TWO-ACCOUNT-CONSOLIDATION handoff s6.7 slippage-mining task) :: **The handoff's premise is false and the execution-quality question is UNANSWERED.** s6.7 says `analysis/trades-enriched.jsonl` "already carries `exit_slippage_vs_mid_before_dollars`, `exit_quote_bid/ask/mid_before/after`, and `exit_quote_lag_before_s` on real fills" and that mining them may make a dedicated lane redundant. Verified: those columns exist in the SCHEMA and are **0 of 388 populated** -- every one is null on every row. The file's own `_meta` already says so: `exit_quote_matched: 0`, `exit_quote_match_rate: 0.0`, `exit_slippage_vs_bid_before_n: 0`. Nobody read it (C7: audit outputs, not exit codes). **ROOT CAUSE, traced to cold reality 2026-08-29 ~18:15 ET:** `trades_enriched.join_exit_quote` joins against `analysis/quote-tape/*.jsonl` -- and **`analysis/quote-tape/` does not exist**. Its producer `setup/scripts/quote_recorder.py` only writes rows when an arm holds an OPEN position during RTH (08:55-16:05 ET weekdays); it was first launched 2026-08-28T17:47 ET -- AFTER Friday's close -- with a 24h bounded duration, so it has **never been alive for a single RTH session** and wrote 0 rows across its whole life (`quote-recorder-status.json`: `last_cycle_rows_written: 0`, `arms_open_last_cycle: []`). That bounded duration expired ~17:47 ET today and **pid 27940 is confirmed DEAD**. Its keepalive `Gamma_QuoteRecorderKeepalive` is currently `State: Disabled` with `NumberOfMissedRuns: 124` -- expected, quiet mode disables non-ESSENTIAL tasks on weekends, and `quiet-mode-restore.json`'s `restore_to_ready` (115 entries) DOES name it, so it SHOULD come back when quiet mode lifts Monday 08:00 local. **ACTION (Monday 2026-08-31, day 1 of the scoring window): verify, do not assume.** After the open, check in order: (1) `Gamma_QuoteRecorderKeepalive` is `Ready`, not `Disabled`; (2) `quote-recorder-status.json` shows a fresh `last_cycle_ts_et` and a LIVE pid; (3) `analysis/quote-tape/2026-08-31.jsonl` EXISTS and is non-empty once any arm holds a position; (4) re-run `setup/scripts/trades_enriched.py` and confirm `exit_quote_match_rate` > 0. **DO NOT build a new slippage-measurement lane** -- the instrument is already built and wired, it has simply never observed a session; building a second one is the duplicate-instrument anti-pattern. Only if step (3) still yields nothing after a full RTH session with an open position is there a real defect to fix, and the fix is in `quote_recorder.py`, not a new lane. âš ï¸ This matters NOW because the September scoring window opens Monday and execution quality (latent live spread was measured at $196-292/day, the figure that makes the book unviable armed) is precisely what it needs to measure -- a window scored with this instrument dark answers the P&L question but not the can-we-actually-fill-this question. :: depends:none :: status:done
> **CLOSED 2026-09-02 16:16 ET (conductor, AFTERHOURS) -- all 4 Monday-gate checks now PASS, instrument confirmed alive and capturing.** (1) `Gamma_QuoteRecorderKeepalive` live-queried: `State: Ready` (not Disabled). (2) `quote-recorder-status.json`: `pid: 9664`, `last_cycle_ts_et: 2026-09-02T16:11:17` (fresh), `last_cycle_ok: true`. (3) `analysis/quote-tape/` now has TWO real session files -- `2026-09-01.jsonl` (310 rows) and `2026-09-02.jsonl` (592 rows, still growing this session). (4) Re-ran `setup/scripts/trades_enriched.py` fresh (403 rows, ctx_match 89.8%, exit_reason_match 97.0%, verify-anchors both PASS) -- new `_meta`: `exit_quote_matched: 15`, `exit_quote_match_rate: 0.0372` (up from the prior 0/388/0.0), `exit_slippage_vs_bid_before_n: 15`, mean exit slippage **-$2.27/trade** vs the resting bid. The low overall rate is EXPECTED and honest per the module's own comment -- the recorder only captures forward from when it started running (2026-08-28+), so it correctly cannot match the 380+ historical rows that closed before it existed; the 15/15 matched are exactly the recent-session rows, which is the instrument doing its job. **No defect found -- step (3)'s fallback ("if still nothing after a full RTH session, the bug is in quote_recorder.py") was never reached.** Additive hygiene done same fire: `analysis/quote-tape/` added to `.gitignore` (raw per-session tick dump, own 90-day retention/pruning already in `quote_recorder.py`; the tracked deliverable is the `exit_quote_*` summary in `trades-enriched.jsonl`, not the raw tape) -- confirmed `quote_recorder.py:273/447/498` already implements `RETENTION_DAYS`-based pruning independently, this just stops it entering git. Curated safety gate 59/59 PASS. Committed `trades-enriched.jsonl` refresh + `.gitignore` change; no trading-path/frozen file touched. **Execution-quality measurement for the September scoring window is now live and accruing daily** -- worth a re-check in ~2 weeks once n is large enough to read the slippage mean with confidence (n=15 today is a directional read, not a verdict).
> **VERIFIED 2026-08-29 ~22:35 ET (Gamma, conductor):** Diagnosis in this item confirmed correct against live state. (1) nalysis/quote-tape/ does NOT exist (confirmed: Test-Path returns False). (2) PID 27940 DEAD -- 24h bounded duration expired ~17:47 ET today as expected. (3) quote-recorder-status.json: last_cycle_rows_written: 0, rms_open_last_cycle: [], skip_reason: "outside RTH window (08:55-16:05 ET weekdays)" -- zero rows ever captured. (4) Gamma_QuoteRecorderKeepalive State: Disabled, NumberOfMissedRuns: 175 -- but IS in quiet-mode-restore.json's 
estore_to_ready (115 entries) and Gamma_QuietMode is Ready firing every 5min; restore will happen at 08:00 ET Monday when maintenance band ends. (5) 	rades-enriched.jsonl _meta confirms: exit_quote_matched: 0, exit_quote_match_rate: 0.0, exit_slippage_vs_bid_before_n: 0 -- all schema columns NULL on all 388 rows. **No fix possible today (Saturday, market closed, instrument not the bug -- needs one live RTH session to collect rows).** Instrument correctly wired; NOT building a second lane (dup-instrument anti-pattern). **Monday gate (automated-verifiable, no J needed):** check Gamma_QuoteRecorderKeepalive is Ready + has a live pid + quote-tape/2026-08-31.jsonl exists after first open position + exit_quote_match_rate > 0 on re-run of 	rades_enriched.py. If those pass this task is DONE. If step (3) still yields nothing after a full RTH with an open position: root cause lives in quote_recorder.py, not a new lane.
  **CLOSED 2026-09-03 00:50 ET (Fable close-out pass):** CLOSED by the 2026-09-02 16:16 ET conductor fire (STATUS entry): `Gamma_QuoteRecorderKeepalive` Ready, `quote-recorder-status.json` fresh/ok, `analysis/quote-tape/2026-09-01.jsonl` + `2026-09-02.jsonl` captured, `trades_enriched.py` now matches 15 exits (rate 0.037, expected -- recorder matches forward only). The fire closed the item in prose but never ticked it here. :: status:done

- [x] QUIET-HOLD-CATCH-UP-SWEEP (HIGH, self-generated, filed 2026-09-02 from the GuardsFull
  2-day darkness root-cause) :: quiet_mode.py disables ~120 tasks for J's evening and HOLDS the
  blackout past its 23:00 ET clock while a fullscreen app is foreground. A trigger inside a hold
  is SKIPPED, and because the task was *Disabled* rather than unavailable, Windows'
  `StartWhenAvailable` cannot recover it -- nothing re-runs it, so the 23:00-01:00 ET maintenance
  band is silently eaten on every evening J games late. Proven by a 7/7 differential over
  2026-09-01 (holds 23:02-23:22 and 00:07-00:42 ET; every task inside missed, every task outside
  ran). DETECTION is shipped (`Gamma_TaskStaleness`, 11fbe474/70be6ae2); the CAUSE is not fixed.
  The obvious fix is a catch-up sweep at the end of `go_loud()`, but it needs a design decision
  this session deliberately refused to guess at, and the constraints are the whole problem:
  (a) WHICH TASKS may be auto-restarted hours late? A report-only producer, yes. `Gamma_KalshiAuto`
  places orders off a next-day weather prediction -- restarting it at 04:00 ET on stale NOAA data
  is a different act from re-running an audit. There is no field in the registry that distinguishes
  them today, so the classification has to be built (or a curated allowlist justified).
  (b) HEAVY tasks cannot simply be restarted: `_stop_heavy_processes()` kills project python on the
  NEXT hold, so a 46-minute GuardsFull started at 23:22 gets killed ~45 minutes in at 00:07 and
  produces nothing, repeatedly, while burning CPU. Either check for runway, or leave HEAVY to the
  staleness report and a deliberate manual start.
  (c) Only NON-REPEATING (daily/weekly) triggers genuinely lose a run -- a 5-minute repeater
  self-heals on its next tick, so the sweep's scope should be derived from trigger cadence, not a
  list. (d) Cap the number started per fire, most-overdue first, and gate on the LOUD/research band
  so a hold lifting at 08:30 ET never launches a grind into premarket. Fail-open, and call it AFTER
  the restore so a bug can never block the re-enable. :: depends:none :: status:filed

  > **SHIPPED 2026-09-02 ~05:45 ET (conductor, AFTERHOURS), commit `6c8d7dc3`.** Implemented all
  > four constraints in `setup/scripts/quiet_mode.py`: `CATCHUP_ELIGIBLE` is a curated 9-name
  > ALLOWLIST (McpDailyAudit, GitHubAudit, SpendSummary, OosCheck, LicenseMonitor, GateExpiryCheck,
  > RosterLiveness, PreregHygiene, RuleBreakAudit) -- every one $0-or-near-$0, report/audit/monitor
  > only, no order placement, no broker/live-money touch, live-verified as `MSFT_TaskDailyTrigger`
  > on the real box. KalshiAuto/FuturesBrokerProbe/GuardsFull/GuardsNightly/ConductorWeekend
  > considered and excluded by name with reasons inline (constraint a/b). `_catchup_sweep()` reuses
  > `scheduled_task_staleness.py`'s `attribute_quiet_hold()`/`parse_quiet_holds()` rather than
  > re-deriving hold-attribution logic (constraint c -- only daily triggers can match by
  > construction of that function). Capped at 5 starts/fire, most-overdue first by
  > `NumberOfMissedRuns`, gated out of the weekday trading band via `_in_trading_band()`, called
  > AFTER the restore in both `go_loud()` and `go_research()` (constraint d). Added idempotency not
  > named in the original spec but required for correctness: a candidate whose real `LastRunTime`
  > has already advanced past the most recent hold's close is skipped, so a 5-minute enforcer
  > cadence cannot restart the same task repeatedly for as long as the hold stays in the 7-day
  > attribution lookback. **This work was promoted from HIGH hygiene to GATE-BLOCKING** by the
  > `CRITERION-5-WINDOW-HAS-ZERO-SLACK` finding below -- resolved that item's fork in the same
  > fire (see its own SHIPPED note). **Verified:** 18 new guard tests
  > (`test_quiet_hold_catchup_sweep_2026_09_02.py`), RED-proofed live (`git stash` the fix -> all
  > 18 fail `AttributeError` on the missing module members; restore -> 18/18 green). No regression:
  > the other 3 quiet_mode test files + scheduled-task-staleness suite = 102 passed; live starvation
  > enumeration test = 5 passed. Curated safety gate 59/59 PASS. `git diff --stat` against the 10
  > frozen trading-path files is empty. **Not done in this fire, left open:** J's own
  > `TASK-SCHEDULER-OPERATIONAL-LOG-DISABLED` one-liner (machine-wide OS setting, not
  > git-revertible); a live end-to-end proof that the sweep actually catches a REAL missed fire
  > (this fire validated behaviour with mocked Task Scheduler responses only -- the first genuine
  > overnight hold will be the live proof, worth a follow-up glance at `quiet-mode.log` for a
  > `CATCH-UP started` line). **Revert:** `git revert 6c8d7dc3` (2 files, fully additive -- no
  > existing function signature changed).
  **CLOSED 2026-09-03 00:50 ET (Fable close-out pass):** SHIPPED 2026-09-02 ~05:45 ET commit `6c8d7dc3` (9-name report-only allowlist, verified 5 tasks caught up). The HEAVY-tier gap it deliberately left (`Gamma_GuardsFull` missed again 2026-09-02 23:15 ET) is tracked under GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-EVENING, in build tonight. :: status:done

- [x] CRITERION-5-WINDOW-HAS-ZERO-SLACK (HIGH, GATE-BLOCKING, filed 2026-09-02 from the off-cadence
  gate run) :: the go-live gate's criterion 5 window `2026-09-01..2026-09-29` contains **exactly 20
  trading days** against a **20 scored-day** bar -- verified against `automation/state/calendar.json`
  (Labor Day 2026-09-07 is the only Sept/Oct holiday). One has elapsed; all 19 remaining must score.
  A single unscored day puts criterion 5 out of reach of its own registered window. The same session
  proved the rig silently loses scheduled days (quiet-mode presence hold skips triggers;
  `StartWhenAvailable` cannot recover a fire missed while the task was Disabled -- `Gamma_GuardsFull`
  dark 08-31..09-02). Those two facts had never been put next to each other, and together they promote
  QUIET-HOLD-CATCH-UP-SWEEP from hygiene to gate-blocking. The extended clock to 10-30 has 3 days of
  slack (43 trading days vs a 40-day bar) and absorbs a miss. DECIDE, in writing: defend the 09-29
  reading (then the catch-up sweep is required work), or state that 10-30 was always the only reading
  that mattered and stop treating 09-29 as a gate date. Evidence: gate run 2026-09-02 05:04 ET,
  criterion 5 `INSUFFICIENT_DAYS days_scored=0/20`.
  **RESOLVED 2026-09-02 05:45 ET -- AND THE 'FORK' WAS NOT ONE.** The question was already
  answered in a pre-registration nobody re-read: `automation/state/prod-shadow-designation.json`,
  written `2026-09-01T20:22:26-04:00` BEFORE any prod-shadow result existed, sets
  `window_start 2026-09-01 / window_end 2026-09-29 / min_days 20` as the bar and says of the
  10-30 clock, verbatim: *"EXTENDED disclosure view only -- it never substitutes for or lowers
  this shorter, harder pass window."* Verified by reading the file directly, not on report.
  So 09-29 IS the registered bar, the zero-slack finding is MORE load-bearing than filed, and
  QUIET-HOLD-CATCH-UP-SWEEP was correctly promoted to gate-blocking (shipped `6c8d7dc3`).
  **Process lesson, on me:** I labelled this a 'genuine fork with no right answer' and declined
  to decide it. It was not a fork -- it was a question with a filed answer I did not go and
  read. Check the window's own designation/pre-registration BEFORE treating its terms as open.
  :: depends:none :: status:resolved

  > **DECIDED 2026-09-02 ~05:40 ET (conductor, AFTERHOURS) -- 09-29 IS the registered bar; this was
  > not actually undecided, it was unread.** `automation/state/prod-shadow-designation.json` was
  > written 2026-09-01T20:22 ET -- BEFORE any prod-shadow result existed -- and says, verbatim:
  > window `2026-09-01..2026-09-29`, `min_days: 20`, and "the PREREG-TIGHT-LADDER-2026-08-28.md
  > 40-day clock (closing 2026-10-30) is tracked as an EXTENDED disclosure view only -- it never
  > substitutes for or lowers this shorter, harder pass window." `go_live_gate.py`'s own generated
  > report (`analysis/go-live-gate.md`) already renders it exactly that way: 09-29 in the Prod-shadow
  > section as the scored bar, 10-30 labelled "(disclosure only, never the pass bar)" in the Plan
  > Reachability table. This is a pre-registration, not a post-hoc read -- it predates every day of
  > evidence in the window it governs, which is the strongest form of "already decided" this project
  > recognizes (OP-11). The system-reminder's "risk EXPANSIONS wait for 10-30" is a SEPARATE clock
  > (the config-freeze trading-path-edit lock, `setup/hooks/doctrine.py`) that happens to share an
  > end date with the freeze's own 09-29 checkpoint by coincidence, not by being the same
  > registration as criterion 5's prod-shadow window -- conflating the two is exactly how this read
  > like an open fork. **Consequence: QUIET-HOLD-CATCH-UP-SWEEP is confirmed gate-blocking, not
  > hygiene, and was shipped this same fire** (commit `6c8d7dc3`, see its own item above) precisely
  > because 19 of the window's 20 required scored days remain and a second silently-lost day would
  > put criterion 5 out of reach of its own pre-registered bar. Nothing else about the gate moves --
  > criterion 1 still fails hard (CI-lower 0.333-0.412 vs a 1.0 bar) regardless of how this reads.
  **CLOSED 2026-09-03 00:50 ET (Fable close-out pass):** RESOLVED 2026-09-02 05:45 ET per this item's own text: `prod-shadow-designation.json` (frozen 09-01 20:22 ET) makes 09-29 binding; the catch-up sweep shipped as gate-blocking work. Nothing further to decide. :: status:done


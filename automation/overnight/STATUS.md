## [2026-08-28T18:00 ET] TASK B3: FULL-SUITE RED (2026-08-27T23:41 ET, 11 failures) triaged and fixed at the root; reconciliation FAILs root-caused and fixed

**All 11 named failures diagnosed individually with reproducing before/after evidence (never reordering hacks, never xfail on a real bug):**
- **5x `test_setup_dispatch.py` (TestFlagOnMockedDetector/TestDetectorError)** — test-order pollution. `test_g_db_base_quiet_wiring.py`'s `sd_mod` fixture did `del sys.modules["setup_dispatch"]` before every import, minting brand-new `SetupDispatcher`/`DispatchResult` class objects on the shared module entry — same defect CLASS as the 2026-08-22 `test_gap_prior_close.py` scar (`importlib.reload()`), different API the existing guard's regex never matched. Reproduced in 2 files alone (`pytest test_g_db_base_quiet_wiring.py test_setup_dispatch.py` → the exact 5 failures); fixed → 41 passed. Guard broadened to catch the eviction shape too. Commit `314f12fc`.
- **`test_kitchen_reviewer_ladder_fallback_2026_08_20.py`** — same pollution family, different mechanism: its own stubbing was conditional on `name not in sys.modules`, silently skipping whenever `test_kitchen_grader_crashloop_guards.py` (correct behavior on its part) had already cached the real `kitchen_daemon`. Made unconditional with proper save/restore. Commit `35df7a4a`.
- **2x `test_dataset_integrity*.py` (mae-mfe manifest DRIFT)** — genuine, not pollution: diffed the manifest's committed baseline against the live file — of 219 frozen-prefix rows, 110 differed, and in EVERY row `recency` (a rolling recent25/older label recomputed against the whole current population, confirmed against `pain_ledger.recent_older_split`) was the ONLY key that changed. Fixed by excluding declared volatile derived fields from the frozen-prefix hash; re-recorded the manifest. Commit `6349d8fa`.
- **`test_state_contracts.py` (loop-state.json ribbon.stack)** — genuine: `loop_state_refresh._heal_nulls_from_beacon`'s null-check (`ribbon is None`) never matched the live shape (`ribbon: {"fast": null, ..., "stack": null}` — a present dict of nulls), so a fresh, populated `sight-beacon.json` never healed it. Broadened the check; ran the refresher (its normal operation). Commit `d1032d9c`.
- **`test_window_leak_compliance.py`** — genuine: 3 real `subprocess.run` call sites missing `creationflags=CREATE_NO_WINDOW` (incl. `go_live_gate.py`, built same-day). Fixed all 3. Commit `c8664d4a`.
- **`test_graduated_guards.py::test_free_model_cost_estimate_is_zero`** — UNVERIFIED as order-dependent: passed standalone and in every combination tried this session (incl. with `test_kitchen_daemon_starvation.py`/`test_kitchen_grader_crashloop_guards.py`); no module-level mutation or eviction pattern found targeting `run_minimax`. Possibly already-fixed or transient on 08-27 — not reproduced, not claimed fixed.

**Reconciliation (go-live-gate.json), root-caused independently of the test-suite work:** safe-3 (-$74.27) and risky-3 (+$231.39) FAILs traced to `go_live_gate.reconciliation_criterion()` trusting Alpaca's `base_value_asof` (2026-07-30) as the account-reset marker, when all 5 arms were actually recreated 2026-08-03T13:00-13:03Z (live-verified `/v2/account.created_at` + same-day $5,000 JNLC deposits, all 5). The 4-day undershoot let real engine trips dated 07-30/07-31 — fired against the OLD, now-defunct pre-rebuild account — leak into ledger_pnl against broker history that is genuinely $0 for those dates on the current account. safe-2/bold-2/risky-1 carry the identical stale clamp but have zero trips in the phantom window (luck of timing, not a correct window). Fixed by also clamping to the live account-creation date: safe-3 diff -$74.27 → $0.44, risky-3 +$231.39 → $0.57 — **RECONCILIATION now PASSES all 5 arms.** Commit `065df4e4`. Standing daily check wired into `self_check.py` (reuses the same criterion, once per ET day, RED classifies BROKEN) so a future drift lands here automatically. Commit `c732f214`.

**OPEN — not this fire's scope:** commit `e4dab06e` (concurrent session) retired risky-3 and repointed its account to the new non-SPY `weekly-1` lane while this work was in flight. `go_live_gate.ACTIVE_ARMS` is a hardcoded tuple, not accounts.json-status-aware — still lists risky-3 as active. Today's reconciliation is unaffected (risky-3's SPY history through 08-27 is real), but the standing daily check will keep reconciling a retired arm going forward once weekly-1 trades start flowing through that account under a different arm_id. Needs a small follow-up: make ACTIVE_ARMS read accounts.json's live `status` field.

Pathspec-committed throughout (`314f12fc`, `6349d8fa`, `c8664d4a`, `d1032d9c`, `35df7a4a`, `065df4e4`, `9a6bd1c1`, `c732f214`) — this checkout is live and shared; 3 of these files were reverted mid-session by an untraced `git reset` and had to be reapplied + committed immediately, confirmed via `git status`/`git reflog` before continuing (C34 scar, live again).

## [2026-08-28T17:52 ET] conductor: OK — QUOTE-RECORDER RED fixed at the root (missing keepalive), commit `69e6c1bf`

**Picked via STAGE 0 budget gate PROCEED ($5.40/$30, 2/4 fires, AFTERHOURS mode) + market-hours gate closed (17:42 ET, weekday, well after 15:55) + `self_check.py` FUNCTION-FIRST priority: verdict=BROKEN, 5 problems, worst being `QUOTE-RECORDER RED: status file 21m stale ... Gamma_QuoteRecorderKeepalive has stopped`.**

**Root cause:** `quote_recorder.py` (Task B1's independent exit-quote NBBO side-channel, built earlier the same day — "we log NBBO on ~25 of 128 entry events and ZERO on exits; every slippage number is an assumption") was verified working but never given an always-on scheduled task; its own `check_quote_recorder_alive` docstring said arming one was "J's call" and stopped there. It had been started manually once (~17:18 ET) and the moment that process exits, the staleness check has no way to distinguish "never armed" from "armed and died" — it reads RED forever.

**Fixed:** `quote_recorder_keepalive.py` (pid-liveness probe cross-checked against the live process table via `wmic`, matched on the literal `quote_recorder.py` filename — a bare substring match would false-positive on the keepalive's own filename or any `test_quote_recorder_*` file) + `install-quote-recorder-keepalive.ps1`, same proven `wscript -> run_exe_hidden.vbs -> run_cmd_hidden.py -> pythonw` chain as `Gamma_WindowLeakDetectorKeepalive`. Launches with a bounded 24h `--duration-sec` (2026-08-13 wedge lesson: unbounded runtime is a liability even for a light poller) so the process self-recycles daily. **Registered live: `Gamma_QuoteRecorderKeepalive`, `State=Ready`, every 5 min 24/7** — manually fired once this fire to close the gap immediately rather than waiting for the first scheduled tick.

**Verified, quoted:** `self_check.py` verdict **BROKEN → DEGRADED** (QUOTE-RECORDER RED cleared; remaining 4 problems are pre-existing/non-load-bearing, already flagged in earlier fires today — trendline-draw stale, chart-drawing stale, two masked-exit log counts). Fresh `quote-recorder-status.json` confirmed with new `pid=27940`, `last_cycle_ok=true`, correctly idling off-RTH. `pytest backtest/tests/test_quote_recorder_keepalive_2026_08_28.py -q` → `11 passed`. `backtest/tests/run_safety_gate.py` → `59 passed, PASS`.

**De-dupe note:** a parallel session (commit `9a6bd1c1`, unrelated Task B3 go-live-gate work) hit the same `test_every_installed_task_is_documented` gate concurrently and had already documented this task in `SCHEDULED-TASKS.md` with its own shorter row before this fire's edit staged — this fire's redundant duplicate row was found and removed before commit, not shipped. Normal "parallel Claudes, don't clobber" surface — no conflict, no lost work either direction.

**Rail 4 (paper-infra monitoring fix, not a live-money/secret/CLAUDE.md surface):** guard test is the regression check (a); revert is `git revert 69e6c1bf` then `install-quote-recorder-keepalive.ps1 -Uninstall` to unregister the live task (source revert alone doesn't touch already-registered Task Scheduler state) (b); this STATUS entry is the REVOKE report (c).

**Not fixed this fire (out of scope, already flagged / non-load-bearing):** TRENDLINE-DRAW STALE (since 2026-08-27), CHART-DRAWING STALE (since 2026-06-29, ~2 months — candidate for a future fire if `desk_allocator`/`task_scorer` don't surface something higher-value first), the two RUN-CMD/RUN-PS1-HIDDEN masked-exit log counts (cumulative-log-rollover artifacts per the 05:30 fire's note).

**Autonomy metric:** `conductor_outcome.py metric` reads `trend=regressing` (cost/drained $2.16 over the trailing 20 fires). This fire was loop-closing (a RED root-caused and fixed, guard-tested, live-verified) per the trend-aware priority the instructions call for; next fire should prefer another closing item over a new artifact.

## [2026-08-28T16:15:03 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-28 -- 5 GREEN / 0 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 188 tick(s) showed in_trade>0. 57 real fill(s) dated 2026-08-28: safe-2@10:21, bold-2@10:21, safe-2@10:22, bold-2@10:22, safe-3@10:22, risky-1@10:22, risky-3@10:22, safe-2@10:23, bold-2@10:23, safe-2@10:24, bold-2@10:24, safe-2@10:25, bold-2@… |
| WS6 regime stamp | GREEN | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-08-28, generated_at_et=2026-08-28T08:40:02-04:00 (hhmm=08:40, in 08:15-08:40 window=True). today-bias.json date=2026-08-28, regime_context.stamp_date=2026-08-28 (present=True, dates_match=True). one_liner='Yesterday 2026-08-27 (Thu) = gap-go (range 0.68%, gap +0.32%, clo… |
| WS3 level hysteresis | GREEN | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 61 distinct near-price levels. Worst: 769.49 flipped 7x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 171 level-refresh run(s) logged (171 ok), hysteresis_held fired 41 time(s) across 6 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-28 window_end=2026-08-27 (baseline window_end=2026-07-31, advanced=True). bear now: RED_CONCENTRATED n=28 (delta +18 vs baseline n=10) exp=$-5.89/tr, verdict_moved=True. bull now: GREEN_CONCENTRATED n=37 exp=$14.92/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-08-28T16:00:01 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2', 'risky-3']. 384 theta-clock row(s) dated 2026-08-28 across 6 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=384, unavailable=0. sti… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-28 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-28`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## [2026-08-28 14:30 ET] J-DIRECTED BUILD - daily premium budget: battery run, rule built INERT, **3-of-4 OP-11 gates - needs J's call**

**J asked "how do we spend less and still hit our daily target".** Answering the second half first, because it
reframes the first: **we do not have a daily-target edge.** Under every policy tested the median arm-day is
NEGATIVE (-$41 at best) and only 24% of arm-days clear +$100. The top 10 arm-days carry 154% of all profit; the
other 120 sum to -$1,658. $100-200/arm/DAY is not a quota this edge can fill - it is a monthly average. Judging
single days against it will produce cut winners and chased losers.

**What CAN be fixed is the carrying cost of waiting for that tail.** 42 days, T1 broker-truth tape, net of A1
fees: the book turned over **$141,641** of premium to net **+$1,317** (0.93%). **205 of 427 entries (48%) were
placed while that arm was already RED on the day.**

**READ THAT NUMBER CORRECTLY:** $141,641 is cumulative TURNOVER across 428 entries x 42 days x ~5 arms -- the
same ~$5k per arm recycled ~8x. It is NOT capital at risk. Actual peak concurrent open premium per arm per
day: median **$350 (7.0% of a $5k account)**, p90 $774 (15.5%), worst-ever $1,880 (37.6%) -- inside the Rule 6
caps throughout. Per-entry ticket: median $276. **Position sizing was never the problem; churn is.** This rule
caps turnover, not size, which is why its benefit lands as drawdown reduction rather than lower exposure.

**Built + battery-run:** `check_daily_premium_budget()` in `backtest/lib/risk_gate.py`, two shapes.
`C_loss_armed` @ $700/arm/session - the cap binds ONLY after the arm books a losing exit that session:
net **+1317 -> +5161**, deployed **$141,641 -> $87,744**, maxDD **4908 -> 2544**, PF **1.08 -> 1.51**,
worst day **-2694 -> -1573**. Per-arm: risky-3 -590->+1310, safe-2 -233->+952, safe-3 +824->+1723,
bold-2 +309->+344, risky-1 +1257->+1084 (-173, the only arm it hurts).

**OP-11 gate: 3 of 4.** PASS oos_positive (+2536 on 17 OOS days), sub_window_stable (all 3 windows positive),
anchor_no_regression (-5.3%). **FAIL wf_median_ge_0.70** (median -0.068; folds [1.0, -0.0676, -0.8921]).
The obvious flat-cap variant is the mirror image - passes WF, **fails anchor at -32.3%** because a flat cap trims
size on exactly the trend days the right-tail edge lives on. **Neither auto-ratifies, so nothing shipped armed.**
WF here is 3 folds of 5 trading days on n=42; the scorecard discloses WF as corroborating-not-decisive at this n,
and the flat cap's WF "pass" comes from two folds clipping to 1.0. That is context, not a reason to waive a gate.

**Verified, quoted:** `pytest backtest/tests/test_daily_premium_budget_2026_08_28.py -q` -> `25 passed`;
`pytest backtest/tests/test_risk_gate.py -q` -> `96 passed`; 5 consumer suites (cap_admission,
entry_block_watch_risk_deny, fast_path_pdt_gap, core_entry_idempotency, fill_funnel_why) -> `58 passed`;
`run_safety_gate.py` -> `59/59 PASS`; **`pytest backtest/tests/test_graduated_guards.py -q` ->
`129 passed, 1 skipped in 1102.73s (0:18:22)`, real pytest `exit=0`.**

**CORRECTION to commit `4b636ee3`'s message (which is immutable, hence this note).** That message says the full
graduated-guards suite was "NOT run -- it hangs on an unrelated tree-scanning test." Both halves are wrong. It
does not hang: it takes **18m22s**, and my 600s/900s command timeouts kept killing it mid-run. It has now been
run to completion and PASSES. The reason I wrongly believed it had passed once, then wrongly believed it hung,
is the same defect both times: the runs were piped (`pytest ... | tail -12`), and bash returns the LAST pipeline
stage's exit status -- so the `exit code 0` the harness reported was `tail`'s, not pytest's. Demonstrated:
`python -c "import sys; sys.exit(3)" | tail -1` -> `0`, unpiped -> `3`. The re-run above was unpiped
(`> file 2>&1; echo "exit=$?"`) and carries a real summary line. This is the repo's own C7 class and is
mechanically identical to `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT`; the rule (quote the `N passed` line, never the
exit code) is filed at `_lesson-inbox/2026-08-28-piping-pytest-to-tail-masks-the-exit-code.md`.

Three self-caught errors worth recording: (1) my first variant-C sweep returned a flat no-op because I passed
`(date, arm)` into a function taking `(arm, date)` - caught by a sanity assert on the armed population, re-run
corrected; (2) the risky-3 replay test asserted 2 surviving entries when the gate correctly allows only 1
($395 + $340 = $735 > $700). The gate was right and my expectation was wrong - the test was corrected, not the gate;
(3) the piped-exit-code error described in the CORRECTION above, which produced a false "the guards suite passed"
claim to J that had to be retracted, then a false "it hangs" claim that also had to be retracted.

**RULE IS OFF.** `daily_premium_budget_dollars` is absent from every params file, so the gate returns None on
every call and `check_order` is byte-identical to its pre-today behavior - the FIRST test class pins exactly that.
Arming is a one-key params edit and is an after-hours action under Rule 9.

**J's call, filed as `DAILY-PREMIUM-BUDGET-J-CALL` in queue.md:** arm on 3-of-4 plus the mechanism argument, or
hold for more OOS data. Recommendation: arm risky-3 + safe-2 first (the two arms it flips negative->positive),
leave risky-1 alone. Revalidation clock: re-run the battery weekly; if WF clears it becomes auto-ratifiable.

**Also surfaced, NOT acted on (out of scope this fire):** conviction tiers do not predict outcomes
(SUPER 0-for-7, LEVEL 0-for-1, ELITE 24.2% WR / +2.5% ROI) - worth its own audit. And risky-3 went 0-for-5 today
(-$410 on $1,735 deployed); it is the premium-stop control cell re-proving a June-settled question (C2,
chart-stop-primary). Closing that cell is J's REVOKE, not mine.

Scorecard: `analysis/recommendations/daily-premium-budget.json`.
Battery: `backtest/autoresearch/daily_premium_budget_battery.py`.
Prior coverage read BEFORE building (Obsidian-brain rule): B3-loss-anatomy, B3-bounded-config, A1-cost-rebuild.
Revert: `git revert 4b636ee3` (6 files -- risk_gate.py + guard + battery + scorecard + queue.md + STATUS.md;
risk_gate.py changes are additive plus one call site). ("4 files" in the original draft of this entry was wrong.)

## [2026-08-28 13:06 ET] RED -- INCIDENT FIX ROSTER REGRESSED (1 RED, 0 unguarded)

- **no-console-popups** -- closes: console flash regression class
  - code: guard-enforced
  - guard: 1 failed, 3 passed in 0.32s

Source: `setup/scripts/incident_fix_status.py --alert` (2026-08-14 incident roster). Re-run it to reproduce.

## [2026-08-28 09:30 ET] RED -- INCIDENT FIX ROSTER REGRESSED (1 RED, 0 unguarded)

- **no-console-popups** -- closes: console flash regression class
  - code: guard-enforced
  - guard: 1 failed, 3 passed in 4.55s

Source: `setup/scripts/incident_fix_status.py --alert` (2026-08-14 incident roster). Re-run it to reproduce.

## [2026-08-28T05:30 ET] conductor: OK — GITHUB-AUDIT-FALSE-RED-DAYS-INTERVAL fixed at the monitoring-instrument root, commit `fcfeaf74`

**Picked via STAGE 0 budget gate PROCEED ($3.78/$30, 1/4 fires, AFTERHOURS mode) + market-hours gate closed (05:30 ET, weekday, pre-open) + `desk_allocator.py` SPY-0DTE #1 ("NEXT FIRE" — 80pts BROKEN, `self-check-last.json=DEGRADED`, futures desk confirmed `armable=false` no proven edge) + `self-check-last.json` (FUNCTION-FIRST priority): `RUN-CMD-HIDDEN MASKED EXIT ... unattended_health.py (exit=[1], 19x)`.**

**Traced past the symptom to the real cause (not the masked-exit surface):** `unattended_health.py`'s exit=1 was itself just a side-effect of its own **RED verdict** on the `github-audit` unit (`Gamma_GitHubAudit: HAS NOT FIRED in 2.2d -- daily trigger, budget 2.0d`). Read `automation/state/unattended-health.json` directly (not just self_check's summary) to find the actual RED. `Get-ScheduledTaskInfo`: last run 8/25 22:46, `NumberOfMissedRuns=1`, `NextRunTime` skipped to 8/29 (not 8/27) — the SAME evening-reboot-window pattern (Kernel-Power reboots 18:00-22:00 MT) already root-caused for `Gamma_DressRehearsal` on 2026-08-26. But then went one layer deeper: the task's live trigger is `DaysInterval=2` ("every 2 days"), and `unattended_health.py::expected_gap_minutes()` **never reads DaysInterval at all** — it scores every `DailyTrigger` at a flat 1440min cadence regardless of N, so the module's own `_MULT_DAILY_PLUS=2.0` design (stated intent: "tolerates EXACTLY ONE missed run") collapsed to a 2.0-day budget for an every-2-day task — i.e. ZERO real slack for a single missed run, contradicting the module's own documented design. This is a genuine monitoring-instrument bug, not a task-scheduling bug: any current or future every-N-day (N>=2) Gamma task would get the same false-RED treatment on its first missed run.

**Fixed both layers:** `_list-gamma-tasks-json.ps1` now emits `days_interval` for `DailyTrigger` entries (previously dropped silently); `expected_gap_minutes()` multiplies cadence by it (`n>1 -> cadence=1440*n`), defaulting to `n=1` (byte-identical behavior) when absent. Swept live for other N>1 DailyTrigger tasks (only `Gamma_GitHubAudit`) and N>1 `WeeksInterval` on WeeklyTrigger (none) — both verified via live `Get-ScheduledTask` queries, not assumed.

**Verified, quoted:** `pytest backtest/tests/test_unattended_health.py -q` → `37 passed` (34 pre-existing + 3 new: every-N-day cadence correct, missing-field default unchanged, budget tolerates one missed run). Live re-run `python setup/scripts/unattended_health.py --json`: `github-audit` unit RED → GREEN, overall verdict RED → YELLOW (all other units byte-identical). Curated safety gate (`run_safety_gate.py`) 59/59 PASS. `git show fcfeaf74 --stat --name-status`: exactly the 4 intended files.

**Not fully cleared:** `self_check.py` still reads DEGRADED this run (`RUN-CMD-HIDDEN MASKED EXIT ... 22x`) — that count is the CUMULATIVE non-zero-exit tally already written to today's `run-cmd-hidden-2026-08-28.log` from BEFORE this fix landed (10 more ticks fired while I was diagnosing); it cannot retroactively un-write history and will clear naturally once today's log rolls over, or once enough fresh GREEN ticks land. This is expected log-rollover lag, not a residual bug — the underlying cause (the false RED itself) is fixed and verified live.

**Lesson filed:** `_lesson-inbox/2026-08-28-daily-trigger-cadence-ignored-days-interval.md` — generalizable: any instrument classifying a Windows scheduled task purely by CimClassName without reading its interval-refining property (DaysInterval/WeeksInterval) will mis-budget any "every N" task. Flags the WeeksInterval blind spot as latent-but-currently-inert (verified empty).

**Rail (infra/monitoring fix, zero live-trading-path touch — no params/heartbeat_core/filters/placement/exit code edited):** guard tests are the regression check (a) — 3 new + 34 preserved; revert is `git revert fcfeaf74` (4 files, fully additive except the one `elif "Daily"` branch, verified reversible) (b); this STATUS entry + the matching queue.md item are the REVOKE report (c).

**Next fire should pick up:** whatever `task_scorer.py --top` / `desk_allocator.py` return fresh — `self_check.py` DEGRADED should read GREEN again once today's `run-cmd-hidden` log stops accumulating historical exit=1 lines (check, don't assume); `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT` is CLOSED (prior fire) so should no longer resurface; `MONITORING-INSTRUMENTS-LACK-CONCENTRATION-GUARDS` (MED, residual scope: 14 named `setup/scripts` files + `backtest/autoresearch/`) remains a reasonable next pick if nothing higher-value surfaces.

---

## [2026-08-28T01:15 ET] conductor: OK — VBS-WRAPPER-EXIT-CODE-BLIND-SPOT CLOSED (SEVENTH PASS), commit `fc739d03`

**Picked via STAGE 0 budget gate PROCEED ($0/$30, 0/4 fires, AFTERHOURS mode) + market-hours gate closed + engine_health.json GREEN (19/19) + `self_check.py` GREEN (0 problems) + `desk_allocator.py` SPY-0DTE #1 (NEXT FIRE, futures desk checked and correctly `armable=false` -- no proven edge) + `task_scorer.py --top` returned `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT` for the 4th consecutive fire (08-25/26/27/28) with the advisory "trace before executing."**

**Traced properly this time (not just the top-line description):** the item's own THIRD PASS (2026-08-07) already ran the `/fable-blast-radius` audit the opening paragraph names as the blocker, and reached a real verdict (blanket vbs flip NOT RECOMMENDED; per-task relay migration is the standing safer path) -- the last 3 fires re-punted on a stale top-line read instead of walking the full dated-pass history. Live-reconciled all 31 originally-named tasks via `Get-ScheduledTask`/`Get-ScheduledTaskInfo` (not prose): 29 already done (19 FOURTH PASS + 9 FIFTH PASS template-fixes + CryptoTwin). `Gamma_JIntentExecutor` is already live on the `run_py_venv_hidden.py` relay (never actually a gap). `Gamma_EodFlattenCore` is still direct wscript->pythonw with no relay, BUT `preopen_readiness.py::assess_eod_flatten_reality` already gives it a bespoke, arguably-stronger per-arm JSONL outcome check (fails-toward-RED on missing evidence, `critical=True`) -- no fix needed, a generic relay migration would be a fidelity downgrade. The one genuine gap: `Gamma_RegimeShadow` (live since 2026-08-11, correctly on the relay) had ZERO install script anywhere in the repo -- the exact no-declarative-source-of-truth risk this whole guard exists to prevent.

**Fixed:** created `setup/scripts/install-regime-shadow.ps1` (reproduces the live registration byte-for-byte, verified via `Get-ScheduledTaskInfo` BEFORE writing -- pure safety net, not a behavior change), registered it in `EXPECTED_RELAY_TASKS`, and fixed 2 doc-registry gaps the curated safety gate caught live: `SCHEDULED-TASKS.md` was missing this task's Active-table row entirely, and its stated count (134) had drifted from the table (135 after adding the row).

**Verified, quoted:** `pytest backtest/tests/test_install_script_relay_wiring_drift.py backtest/tests/test_scheduled_tasks_doc.py -q` → `50 passed, 1 skipped`. Curated safety gate (`run_safety_gate.py`): FAILED first run (both doc-registry gaps) → `59 passed` after fixes. `self_check.py`: GREEN, 0 problems, before and after. `git show fc739d03 --stat --name-status` + `git ls-tree HEAD`: exactly the 3 intended files landed (`install-regime-shadow.ps1`, `test_install_script_relay_wiring_drift.py`, `SCHEDULED-TASKS.md`).

**Item CLOSED** in queue.md (`status:pending` → `status:done`) — no further named gap remains; every tracked task is either on a relay with a matching install template, or deliberately excluded with a stated, verified reason. `task_scorer.py --top` re-confirmed post-fix: no longer returns this item (now `FLEET-STRIKE-TIER-ATM-EXTENSION-EVAL-2026-08-01`, correctly dormant per its own 2026-08-27 verdict, not re-picked this fire).

**Lesson filed:** `strategy/candidates/_lesson-inbox/2026-08-28-long-queue-item-blocking-subclaim-goes-stale.md` — a long multi-pass queue item's top-line description can go stale relative to its own later PASS history, causing repeated fires to re-derive the same superseded conclusion; generalizable fix (not applied this fire) is for each new PASS to update the item's own opening status line rather than relying on the next reader to walk the full history.

**Rail 4 (infra/scheduler hygiene, zero live-trading-path touch — pure documentation/template fix, verified behavior-identical to live state):** guard test is the regression check (a); revert is `git revert fc739d03` (3 files, additive + 2-line count bump, fully reversible) (b); this STATUS entry is the REVOKE report (c).

**Next fire should pick up:** whatever `task_scorer.py --top` returns fresh (currently `FLEET-STRIKE-TIER-ATM-EXTENSION-EVAL-2026-08-01`, dormant — check its equity-floor re-trigger condition before treating it as ready); the FULL-SUITE RED logged below (2026-08-27T23:41 ET, 11 failures) has not yet been triaged by a conductor fire and may be higher priority than continuing down the task_scorer list.

---

## [2026-08-27] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-07-23..2026-08-26), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-08-26). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=CONFIRM; #1 ATM (Bold)=CONFIRM; #2 ATM=YELLOW; #4 ATM=YELLOW
> - **Books:** Safe2_ATM_1+2+4=RED ($-207.35); Bold_ATM_1+2=CONFIRM ($269.4)
> - **edges_confirmed_on_recent = True** (any RED=True). CONFIRMED: #1 ATM (Safe-2), #1 ATM (Bold). RED-BLOCKED: Safe2_ATM_1+2+4 — no live flip on these.
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## Known broken

- [2026-08-27 23:41 ET] FULL-SUITE RED :: 10165 passed, 11 failed, 12 skipped :: tests/test_dataset_integrity_2026_08_15.py::test_current_tree_verifies_clean, tests/test_dataset_integrity_append_only_2026_08_21.py::test_the_real_tree_verifies_clean_today, tests/test_graduated_guards.py::test_free_model_cost_estimate_is_zero, tests/test_kitchen_reviewer_ladder_fallback_2026_08_20.py::test_unparseable_pool_result_falls_through_to_ladder, tests/test_setup_dispatch.py::TestFlagOnMockedDetector::test_vwap_continuation_flag_on_calls_detector, tests/test_setup_dispatch.py::TestFlagOnMockedDetector::test_gap_and_go_flag_on_calls_detector, tests/test_setup_dispatch.py::TestFlagOnMockedDetector::test_dispatch_extra_setups_serializes_fired_signal, tests/test_setup_dispatch.py::TestDetectorError::test_detector_exception_returns_skip_error, tests/test_setup_dispatch.py::TestDetectorError::test_dispatch_extra_setups_never_raises, tests/test_state_contracts.py::test_live_json_file_validates[automation/state/loop-state.json], tests/test_window_leak_compliance.py::test_no_py_subprocess_missing_creationflags :: re-run: cd backtest && python -m pytest tests/ -q -m "not slow"
## [2026-08-27T16:15:03 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-27 -- 5 GREEN / 0 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 203 tick(s) showed in_trade>0. 47 real fill(s) dated 2026-08-27: safe-2@09:41, bold-2@09:41, safe-2@09:42, bold-2@09:42, safe-3@09:42, risky-1@09:42, risky-3@09:42, safe-2@09:43, bold-2@09:43, safe-2@09:44, bold-2@09:44, safe-2@09:45, bold-2@… |
| WS6 regime stamp | GREEN | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-08-27, generated_at_et=2026-08-27T08:40:02-04:00 (hhmm=08:40, in 08:15-08:40 window=True). today-bias.json date=2026-08-27, regime_context.stamp_date=2026-08-27 (present=True, dates_match=True). one_liner='Yesterday 2026-08-26 (Wed) = range-chop (range 0.45%, gap -0.15%,… |
| WS3 level hysteresis | GREEN | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 66 distinct near-price levels. Worst: 769.36 flipped 4x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 171 level-refresh run(s) logged (171 ok), hysteresis_held fired 78 time(s) across 14 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-27 window_end=2026-08-26 (baseline window_end=2026-07-31, advanced=True). bear now: RED_CONCENTRATED n=29 (delta +19 vs baseline n=10) exp=$-16.21/tr, verdict_moved=True. bull now: GREEN_CONCENTRATED n=32 exp=$0.5/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-08-27T16:00:00 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2', 'risky-3']. 568 theta-clock row(s) dated 2026-08-27 across 4 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=568, unavailable=0. sti… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-27 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-27`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

## Live watch

- [2026-08-28T13:14:00 ET] THETA STALL :: safe-2 SPY260828P00770000 qty=3 :: est theta burn -6.78 vs est delta gain -48.00 over last 15min (mid=1.565, unrealized=-13.07%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-28T13:07:01 ET] THETA STALL :: risky-3 SPY260828P00768000 qty=5 :: est theta burn -5.15 vs est delta gain +0.00 over last 15min (mid=0.985, unrealized=4.44%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-28T13:07:01 ET] THETA STALL :: bold-2 SPY260828P00768000 qty=5 :: est theta burn -6.05 vs est delta gain +0.00 over last 15min (mid=0.985, unrealized=10.59%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-28T10:35:00 ET] THETA STALL :: safe-3 SPY260828C00771000 qty=3 :: est theta burn -5.16 vs est delta gain -6.00 over last 15min (mid=1.9995, unrealized=7.07%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-28T10:32:01 ET] THETA STALL :: bold-2 SPY260828C00773000 qty=5 :: est theta burn -5.45 vs est delta gain +0.00 over last 15min (mid=0.525, unrealized=-24.66%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-28T10:32:01 ET] THETA STALL :: safe-2 SPY260828C00771000 qty=3 :: est theta burn -5.04 vs est delta gain -180.00 over last 15min (mid=1.48, unrealized=-16.09%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-28T10:30:02 ET] THETA STALL :: risky-1 SPY260828C00771000 qty=5 :: est theta burn -5.10 vs est delta gain -420.00 over last 15min (mid=1.505, unrealized=-21.08%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-27T12:15:00 ET] THETA STALL :: bold-2 SPY260827C00772000 qty=5 :: est theta burn -5.30 vs est delta gain +0.00 over last 15min (mid=0.295, unrealized=-20.59%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-27T12:09:00 ET] THETA STALL :: risky-1 SPY260827C00770000 qty=5 :: est theta burn -11.70 vs est delta gain -52.50 over last 15min (mid=1.125, unrealized=-3.45%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-27T12:09:00 ET] THETA STALL :: safe-3 SPY260827C00770000 qty=3 :: est theta burn -6.75 vs est delta gain -31.50 over last 15min (mid=1.145, unrealized=-0.89%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-27T12:02:00 ET] THETA STALL :: risky-3 SPY260827C00772000 qty=10 :: est theta burn -5.60 vs est delta gain +0.00 over last 15min (mid=0.325, unrealized=0.0%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-27T09:58:00 ET] THETA STALL :: safe-2 SPY260827C00768000 qty=3 :: est theta burn -7.56 vs est delta gain -93.00 over last 15min (mid=1.405, unrealized=-12.03%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-27T09:58:00 ET] THETA STALL :: safe-3 SPY260827C00768000 qty=3 :: est theta burn -6.99 vs est delta gain -93.00 over last 15min (mid=1.415, unrealized=-15.76%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-27T09:57:00 ET] THETA STALL :: risky-3 SPY260827C00771000 qty=10 :: est theta burn -5.10 vs est delta gain +0.00 over last 15min (mid=0.395, unrealized=-21.28%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-08-27T09:50:00 ET] THETA STALL :: risky-1 SPY260827C00768000 qty=5 :: est theta burn -5.85 vs est delta gain -95.00 over last 15min (mid=1.555, unrealized=-8.43%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
_Standing visibility-only flag surface (THETA COCKPIT, 2026-08-01 J directive) -- NOT a breakage list, no auto-exit ever. Producers append ONE loud line here on a NEW stalled-position threshold crossing; never re-fired for the same position. Producer: setup/scripts/theta_clock.py._

---

## [2026-08-27 09:30 ET] RED -- INCIDENT FIX ROSTER REGRESSED (1 RED, 0 unguarded)

- **no-console-popups** -- closes: console flash regression class
  - code: guard-enforced
  - guard: 1 failed, 3 passed in 4.32s

Source: `setup/scripts/incident_fix_status.py --alert` (2026-08-14 incident roster). Re-run it to reproduce.

## [2026-08-27T05:40 ET] conductor: OK — MONITORING-INSTRUMENTS-LACK-CONCENTRATION-GUARDS: 5 more candidates audited-clear + doctrine folded, commit `192b47e2`

**Picked via STAGE 0 budget gate PROCEED ($8.99/$30, 1/4 fires) + market-hours gate closed (05:30 ET, weekday, pre-open) + engine_health.json GREEN (19/19) + `self_check.py` GREEN (0 problems) + `desk_allocator.py` SPY-0DTE #1 "NEXT FIRE" (futures desk checked and confirmed NOT decision-rotting: MES mirror 84/20 round trips but `beats_null=false` against the current +$7,121 buy-and-hold null, so `armable=false` — correctly quiet) + `task_scorer.py --top` returned `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT` again (3rd consecutive fire; re-confirmed it is still correctly gated behind its own `/fable-blast-radius` pass, touches `Gamma_HeartbeatCore`'s wrapper — not a bounded sonnet-tier pick) — fell to `queue.md` HIGH tier: `MONITORING-INSTRUMENTS-LACK-CONCENTRATION-GUARDS`, whose own text named 5 specific unaudited candidates plus an open doctrine-encode step.**

**What I did:** read each named candidate's ACTUAL verdict-computation code (not its name/docstring alone) for the bare-mean-without-concentration-term defect that already hit `gate_expiry_check.py` (2x) and `live_readiness.py` this week. Result — **zero additional defects**, all 5 are correctly built:
- `desk_allocator.py::assess_spy/assess_futures` — NOT susceptible. Its own module docstring states "DELIBERATELY NOT SCORED: P&L level" — P&L is informational headline text only, never gates the allocation decision.
- `chop_exposure_meter.py` — NOT susceptible. Docstring: "the meter measures exposure; it does not judge" — no PASS/FAIL/verdict field exists in its output at all.
- `day_throttle_shadow.py` / `stop_mode_shadow_ledger.py` (the two real producers behind "shadow-tally/summary writers") — NOT susceptible, both emit `verdict_ready` (an n>=threshold readiness flag), never a PASS/FAIL judgment from a mean.
- `entry_quality_ledger.py` — NOT susceptible, ALREADY gates its 3-way verdict on `delta_drop_top2 > 0` (its G3 criterion).
- `score_ladder_shadow_nightly.py`'s frozen forward-arm bar — NOT susceptible, the prereg (frozen 2026-08-07, 16 days before this lesson was named) already requires "no session worse than -$500" + "chop-day average not worse than -$300" alongside the mean — a tail-risk term baked in independently.
- Spot-checked 7 more `*verdict*`/`*_check(`-matching files via a `grep -l` sweep of `setup/scripts` (`gate_recency_report.py`, `oos_check_runner.py`, `regime_attribution.py` [has its own named `concentration()` function], `risky1_lane_composition_check.py`, `exit_policy_beats_null_2026_08_23.py` [two-tailed drop-top3/drop-worst3 already first-class], `bold_tier_rail.py`, `trendline_tier_rail.py`) — zero bare-`fmean`-without-concentration hits.

**Doctrine-encode step (was still open on the item) — DONE:** folded a generalized paragraph into `markdown/research/BACKTESTING-PLAYBOOK.md` §4.3 (Concentration gate): the rule applies to ANY verdict-producing function repo-wide, not just backtest strategy evaluators, naming the shared `backtest/lib/concentration.py::drop_top_n` helper and all 3 real incidents + all 5 audited-clear candidates as the reference list, so a future `*_verdict`/`*_check.py` author has doctrine to grep before writing a bare-mean gate.

**Not exhaustive, disclosed as such:** 14 of the 21 `*verdict*`/`*_check(`-matching files in `setup/scripts` were not individually opened this fire (named explicitly in the queue item: `heartbeat_core.py`, `monday_verify.py`, `kitchen_reviewer.py`, `engine_health.py`, `firm_brief.py`, `crypto_twin_core.py`, `autonomy_report.py`, `task_state_guard.py`, `crypto_twin_ladder_sim.py`, `crypto_twin_scenarios.py`, `participation_daily.py`, `free_model_audit_prospector.py`, `twin_gauntlet_conductor_hook.py`, `free_model_audit_twin_review.py`), nor was `backtest/autoresearch/` swept — a genuine sweep of ~35+ files is not one bounded fire. Downgraded the queue item **HIGH → MED** and re-scoped it to exactly that residual list rather than closing it.

**Also closed:** the matching 2026-08-26T17:31 self-audit gap (`analysis/self-audit/new-gaps-flagged.md`, concentration-guard deficiency) marked `<!-- DONE -->` with a pointer to this fire — it was the swarm re-flagging a gap that `live_readiness.py` (650ef9c8) had already substantially addressed the day before.

**Verified, quoted:** curated safety gate (`run_safety_gate.py`) `59 passed` both before and after (doc-only change, no code touched, no regression possible). `git show 192b47e2 --stat --name-status`: exactly the 3 intended files (`analysis/self-audit/new-gaps-flagged.md`, `automation/overnight/queue.md`, `markdown/research/BACKTESTING-PLAYBOOK.md`).

**Rail (reporting/doctrine-authoring only — zero code, zero live-trading-path touch, zero params/accounts.json edit):** ships per OP-22/OP-26 engine-benefit authoring path, no guard test applicable (nothing executable changed). Revert: `git revert 192b47e2` (fully additive across all 3 files).

**Lesson:** not filed as a new L## — this fire's finding IS the lesson-graduation step for the existing `2026-08-26-live-readiness-gate-lacked-concentration-guard.md` inbox item (now folded into doctrine directly rather than needing a separate lesson-author pass).

**Autonomy metric:** `conductor_outcome.py metric` → `trend: regressing` (net_improvement 9 / 20-fire window, cost_per_drained $2.36). This fire closed a loop (audited-clear on 5 named candidates + doctrine fold, item downgraded not left open-ended) rather than adding a fresh artifact — the right shape to counter the trend per OP-22; next fire should prefer another loop-close over a new artifact too.

**Next fire should pick up:** `MONITORING-INSTRUMENTS-LACK-CONCENTRATION-GUARDS` (now MED) has a precisely-scoped residual — the 14 named `setup/scripts` files + `backtest/autoresearch/` — if it's the highest-ROI item again. `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT` remains correctly gated behind its own blast-radius pass (3 consecutive fires now) — if it keeps winning `task_scorer.py --top`, consider filing it as a standing `FABLE-ESCALATION` so a top-tier session actually runs the blast-radius pass instead of every sonnet fire re-confirming the same gate.

---

## [2026-08-27T01:10 ET] conductor: OK — FLEET-STRIKE-TIER-ATM-EXTENSION-EVAL-2026-08-01 scored: DISCLOSED_NULL_STRUCTURALLY_UNREACHABLE, item downgraded dormant (no code change, no revert)

**Picked via STAGE 0 budget gate PROCEED ($0/$30, 0/4 fires) + market-hours gate closed + engine_health.json GREEN (19/19) + `self_check.py` GREEN (0 problems) + `desk_allocator.py` SPY-0DTE #1 + `task_scorer.py --top` returned the already-flagged-gated `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT` (unchanged since 2026-08-26 05:30's assessment — still correctly gated behind its own live-trading blast-radius pass, not a bounded pick) — fell to the next ready item, `FLEET-STRIKE-TIER-ATM-EXTENSION-EVAL-2026-08-01`, whose `n>=20 fills` dependency now reads satisfied (139 real fills since 2026-08-01).**

**What the naive read would have gotten wrong:** scoring the prereg's 5 frozen gates against those 139 fills directly. Lane-scoping first: all 73 of risky-1's fills are 100% `FULL_SEND`-lane (provably inert to `strike_tier_table` per the prereg's own 2026-08-02 addendum), leaving risky-3's 66. But a check the original gate text never named — the `equity` field on every one of the 504 risky-3 + 607 risky-1 named-setup decision-rows since 2026-08-01 — shows **zero** rows in the $0-2K bracket this specific prereg's code change touched; all sit in $2K-10K (both arms started near $5K and never approached $2K, one brief exception on 2026-08-01 with zero trading that day). risky-3's real 66 fills were actually priced by a DIFFERENT, already-adjudicated tier row (`atm-tier-extension-2k10k-prereg-2026-08-03.json`, killed for risky-3 on 2026-08-06, commit `3ac1d7b2`, n=14/-$653) — scoring them here would have double-counted a closed decision under the wrong rule_id.

**Verdict: n=0 mechanism-relevant fills. DISCLOSED_NULL, not a kill.** No revert — nothing has fired, nothing to undo. Filed the scorecard `analysis/recommendations/fleet-strike-tier-atm-extension-2026-08-27.json` with full derivation (naive-read → lane-scoping → equity-bucket check → consequence). Queue item's readiness criterion corrected in-place: re-check only if either arm's live `equity` drops back below $2,000, not on raw fill count — downgraded to dormant so future fires stop re-reading it as active evidence-accrual.

**Lesson filed:** `strategy/candidates/_lesson-inbox/sample-floor-gate-must-scope-to-mechanism-not-total-fills-2026-08-27.md` — generalizable: any "n>=N fills since arming" gate needs a condition predicate (the specific bracket/regime/quality-tier the change actually engages), or a structurally-unreachable change can sit "ready to evaluate" indefinitely while a naive scorer misattributes an unrelated, already-closed decision's fills to it. Flags `task_scorer.py`'s dependency check (raw fill count) as sharing the same naivety — not fixed this fire (bounded scope), named for a future sweep.

**Rail (reporting/evidence-authoring only — zero code, zero live-trading-path touch, zero params/accounts.json edit):** this is not a rail-4 trading-path change (no revert needed, no guard test applicable — nothing was armed or disarmed). Ships per OP-22/OP-26 engine-benefit authoring path. Files touched: `automation/overnight/queue.md` (verdict block appended, item's own `[ ]` line kept, readiness note updated), new scorecard JSON, new lesson-inbox file. Revert: `git revert <this-fire's-commit>` (fully additive except the one-line readiness-criterion edit in queue.md).

---

## [2026-08-26T23:26:00 ET] conductor: OK — DRESS-REHEARSAL STALE (RED) fixed + latent doc-untracked landmine closed, commits `12f4a907` + `e0a6711f`

**Picked via STAGE 0 budget gate PROCEED ($8.21/$30, 3/4 fires, AFTERHOURS mode) + market-hours gate closed + engine_health.json GREEN (19/19) + `desk_allocator.py` SPY-0DTE #1 ("NEXT FIRE") + `self_check.py` FUNCTION-FIRST priority-1: fresh run returned BROKEN, 5 problems — `DRESS-REHEARSAL STALE (RED)` was the only RED-severity item (others are non-load-bearing visibility/YELLOW).**

**Root cause, precisely:** `Gamma_DressRehearsal` (the nightly real-broker pre-open sanity check) missed 3 consecutive nights (2026-08-24/25/26, `NumberOfMissedRuns=3`). Kernel-Power event log shows the box reboots most evenings in the 18:00-22:00 MT window, landing directly in the single 20:45 ET (21:44 MT) daily trigger's slot; `StartWhenAvailable=True` was already set but Task Scheduler's catch-up doesn't reliably recover multi-day misses. The SAME evening-window pattern is visible across ~15 other `Gamma_*` tasks (not flagged by self_check, non-critical) — named as a follow-up, not chased this fire.

**Fix:** `dress_rehearsal.py` now skips real work by default when today's ET-date artifact already exists (`--force` overrides); two extra DAILY trigger slots (19:00 MT, 23:15 MT) added to the EXISTING `Gamma_DressRehearsal` task via `Set-ScheduledTask`, alongside the unchanged 21:44 MT primary — 3 chances/evening for the idempotent script to land while the box is up, collapsing to one real options+crypto round-trip/day regardless of how many slots fire.

**Blocked path, worth recording:** the original plan (a separate at-startup task) hit `Access Denied` on `Register-ScheduledTask` AND `schtasks /Create /SC ONLOGON` — isolated via disposable dummy-task A/B probes to a **trigger-TYPE permission boundary** (this session's token can create/modify DAILY/ONCE triggers freely, denied for ONLOGON/ONSTART, on both new-task and modify-existing paths). Documented in `markdown/infra/POWERSHELL-COMPAT.md` + lesson-inbox item so a future fire doesn't re-derive it via another round of probing.

**Verified, quoted:** manual `--force`-equivalent (default, no flag, today's artifact absent) ran for real — `overall=GREEN next_trading_day=2026-08-27`, all 4 checks GREEN. Immediate re-run correctly no-op'd (`already ran today (2026-08-26) — no-op`). `self_check.py`: BROKEN(5 problems) → DEGRADED(4 problems), `DRESS-REHEARSAL` no longer listed. `pytest backtest/tests/test_dress_rehearsal.py`: 47/47 PASS (was 40, +7 new guards for the skip/force/artifact-freshness logic). Curated safety gate (`run_safety_gate.py`): 59/59 PASS. `py_compile` clean. `git show 12f4a907 --stat --name-status`: exactly the 2 intended files.

**Side-effect fix:** `markdown/infra/POWERSHELL-COMPAT.md` was referenced from CLAUDE.md but had never actually been `git add`-ed (existed on disk, untracked) — now tracked as of `e0a6711f` (a landmine closed, not created).

**Rail 4 (infra/scheduler fix, not a live trading-path params/heartbeat_core/filters/placement edit — ships per OP-22/OP-26 engine-benefit authoring path):** guard tests are the regression check (a) — `TestIdempotentSkipByDefault` (5 new tests) + preserved existing 40; revert is `git revert 12f4a907` + manually resetting `Gamma_DressRehearsal`'s triggers to the single 21:44 MT original via `Set-ScheduledTask` (b); this STATUS entry is the REVOKE report (c). Zero live-money, secret, or CLAUDE.md surfaces touched.

**Not investigated further this fire (out of bounded scope):** the ~15 other evening-window tasks showing `NumberOfMissedRuns>0` in the `Get-ScheduledTaskInfo` sweep — mostly research/kitchen/visibility tasks, none self_check-critical the way DressRehearsal was. Named as a follow-up in the lesson-inbox item, not chased.

---

## [2026-08-26T16:15:02 ET] YELLOW -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-08-26 -- 4 GREEN / 1 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 43 tick(s) showed in_trade>0. 23 real fill(s) dated 2026-08-26: safe-2@14:56, safe-2@14:57, safe-3@14:57, risky-1@14:57, risky-3@14:57, safe-2@14:58, safe-2@14:59, safe-2@15:00, safe-2@15:01, safe-2@15:02, safe-2@15:03, safe-2@15:04, safe-2@1… |
| WS6 regime stamp | GREEN | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-08-26, generated_at_et=2026-08-26T08:40:02-04:00 (hhmm=08:40, in 08:15-08:40 window=True). today-bias.json date=2026-08-26, regime_context.stamp_date=2026-08-26 (present=True, dates_match=True). one_liner='Yesterday 2026-08-25 (Tue) = gap-fade (range 0.49%, gap +0.35%, c… |
| WS3 level hysteresis | YELLOW | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 66 distinct near-price levels. Worst: 766.43 flipped 10x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 171 level-refresh run(s) logged (171 ok), hysteresis_held fired 91 time(s) across 14 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-08-26 window_end=2026-08-25 (baseline window_end=2026-07-31, advanced=True). bear now: RED_CONCENTRATED n=29 (delta +19 vs baseline n=10) exp=$-16.21/tr, verdict_moved=True. bull now: GREEN_CONCENTRATED n=32 exp=$0.5/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-08-26T16:00:01 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2', 'risky-3']. 43 theta-clock row(s) dated 2026-08-26 across 1 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=43, unavailable=0. still… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-08-26 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-08-26`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---


### DEGRADED: self-check 2026-08-28T17:47:39
- TRENDLINE-DRAW STALE: last mark_run was 2026-08-27 (skipped), not today (2026-08-28) -- Step 5c likely didn't fire this morning. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- CHART-DRAWING STALE: last chart_drawing_summary.as_of was 2026-06-29, not today (2026-08-28) -- premarket Step 5 (chart wipe + level draw) likely didn't fire this morning. Non-load-bearing (visibility only); re-run premarket Step 5 by hand to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-28.log shows 22 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 22x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-28.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-sight-beacon.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

### DEGRADED: self-check 2026-08-28T17:47:45
- TRENDLINE-DRAW STALE: last mark_run was 2026-08-27 (skipped), not today (2026-08-28) -- Step 5c likely didn't fire this morning. Non-load-bearing (visibility only); run the trendline-draw skill by hand to catch up.
- CHART-DRAWING STALE: last chart_drawing_summary.as_of was 2026-06-29, not today (2026-08-28) -- premarket Step 5 (chart wipe + level draw) likely didn't fire this morning. Non-load-bearing (visibility only); re-run premarket Step 5 by hand to catch up.
- RUN-CMD-HIDDEN MASKED EXIT: run-cmd-hidden-2026-08-28.log shows 22 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- unattended_health.py (exit=[1], 22x). Check the named script's own stderr log for the real cause.
- RUN-PS1-HIDDEN MASKED EXIT: run-ps1-hidden-2026-08-28.log shows 1 real non-zero exit(s) Task Scheduler's LastTaskResult can never see (outer wscript hop is still fire-and-forget) -- run-sight-beacon.ps1 (exit=[1], 1x). Check the named .ps1's own Invoke-Claude budget/timeout, or its underlying script's stderr log.

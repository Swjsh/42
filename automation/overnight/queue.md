# OVERNIGHT TASK QUEUE â€” conductor work backlog

> Format: `- [ ] <id> (<priority>) :: <description> :: depends:<...> :: status:<pending|in_progress|blocked>`
> **OP-22 discipline:** this file holds REAL, drainable work. Machine-generated regression/harvest noise lives in `## Archived 2026-06-19` (rolled up) and verbatim in `queue-archive-2026-06-19.md`. When you finish an item, move it to `## Completed`. When you add HARVEST/REGFAIL auto-noise, it does NOT belong here unless it names a concrete, actionable engine fix.
>
> **Triaged 2026-06-19** (OP-22 compound-don't-accumulate pass): 172 stale auto-generated CRITICALs + harvest data-points archived; gym is 88/88 green (CONTEXT-107/109) so the EDGE_REGRESSION_FAIL "CRITICALs" were false alarms that nothing drains. Active backlog below is the genuinely-real remainder, ranked by leverage. Full pre-triage file preserved verbatim at `automation/overnight/queue-archive-2026-06-19.md`.

---

- [x] AUTONOMY-METRIC-ZERO-ENTERS-08-31 (MED, filed 2026-09-01 conductor AFTERHOURS) :: `conductor_outcome.py metric` shows `trend=regressing`, driven by `function_latest.enters_last_trading_day=0` for 2026-08-31 (both accounts). Not investigated this fire (scope discipline -- a different LOW item was already picked and shipped). Check: was 08-31 a legitimate quiet day (doctrine: sitting out is a valid day, `feedback_sitting_out_is_a_valid_day_2026_08_12`) or a funnel miss (`self_check.py::check_fill_funnel` / `check_engine_tradeability` should already have flagged a real miss as BROKEN -- if neither did, that itself is worth checking). Cross-check `automation/state/core-decisions.jsonl` for 08-31 RTH rows and `key-levels.json`/`today-bias.json` freshness that day before concluding either way. :: depends:none :: status:pending
  **INVESTIGATED 03:47 ET 2026-09-03 (Sonnet, Fable read) -- NOT a clean sit-out, metric NOT patched:** `check_engine_tradeability` on the 08-31 tape: 386 ticks, 0 ENTER, **55 ticks scored bear >= 9 with no trigger fired**; the same flag fired in production mid-session (`self-check-2026-08-31.log`, BROKEN). `analysis/refusals/2026-08-31.json`: 50 gate-blocked episodes, net-negative counterfactual (refusing was right). Rule 2 says bias != trigger, so high score with no trigger is legal -- but 55 such ticks in one session is either a real day the detector could not name a level rejection on, or a detector gap; only a chart replay of 08-31 settles it. `conductor_outcome.py`'s `regressing` label stands until then. Filed BEAR-08-31-HIGH-SCORE-NO-TRIGGER-REPLAY. :: status:pending
  **RESOLVED 03:57 ET 2026-09-03 (Fable):** the replay above shows every high-score tick was refused by blocker 8 (VIX floor), a ratified gate -- a sanctioned sit-out (feedback_sitting_out_is_a_valid_day). The remaining defect is in the METRIC: `conductor_outcome.py` labels a day `regressing` on enters=0 without asking whether the zero was gate-refused. Fix (non-trading-path, spawned): a day with >= N RTH ticks, 0 enters, and >= 1 high-score tick where every refusal carries a gate blocker id grades `SAT_OUT_GATED` (neutral, with the dominant blocker id in the reason); a day with 0 enters and 0 high-score ticks grades `QUIET`; only enters=0 with high-score ticks and NO blocker recorded stays `regressing`. :: status:in_progress
  **CLOSED 04:12 ET 2026-09-03 (Sonnet, Fable-verified 48 passed):** `conductor_outcome._grade_zero_enter_day` + `_filtered_for_trend`: a zero-enter day with >= 100 RTH ticks and >= 1 tick scored >= 9 (the `self_check` convention; rows carry no threshold field) where EVERY such tick carries a blocker grades `SAT_OUT_GATED` (reason = dominant blocker + counts); 0 high-score ticks = `QUIET`; high-score ticks with no blocker = `regressing`. SAT_OUT_GATED/QUIET days drop out of the trend comparison (they had been scoring 0.0 against the other half). Live: 08-31 -> `SAT_OUT_GATED -- blocker 8 refused 110/174 ticks scored >= 9`; 09-02 (33 enters) byte-identical, grade null. `autonomy-metric.json` regenerates on the next scheduled run. **CORRECTION to the replay note above:** 09-01 was NOT a zero-enter day -- the ledger shows 13 ENTER_BEAR verdicts and 4 trades.csv fills on 09-01 (120 bear>=9 ticks blocked + 14 unblocked); the '60 refused ticks / 12 episodes' were real but morning-only. That 09-01 entered bear with VIX ~16 also means the replay's reading of blocker 8 as 'VIX > 17.30 AND rising' is incomplete or tiered -- UNVERIFIED, noted on the F8 item. :: status:done

- [x] BEAR-08-31-HIGH-SCORE-NO-TRIGGER-REPLAY (MED, engine-edge investigation, freeze-compatible -- replay + report only, no filter/trigger changes; filed 2026-09-03 03:47 ET) :: On 2026-08-31 the engine scored bear >= 9 on 55 of 386 ticks and fired no trigger; self_check flagged it BROKEN mid-session. Replay the session bar by bar with `backtest/tools/historical_replay.py` (or the sole-blocker miner's per-tick path) and answer, per high-score cluster: (1) which trigger conditions were evaluated (level_rejection / sequence_rejection / trendline_rejection) and which sub-condition failed (no level within band? wick/body rule? min_triggers?); (2) whether a human would call the price action a level rejection (attach the SPY 5-min bars + the key-levels.json of that day); (3) whether the same signature appears on other zero-enter days in the September window (09-01, 09-02). Output `analysis/deep-research/BEAR-08-31-NO-TRIGGER-REPLAY.md`. If the answer is 'a level was missing from the feed', that is a level-producer bug (freeze-compatible fix); if 'the trigger rule is too strict', that is a prereg for 10-30, not a change. :: depends:none :: status:filed
  **CLOSED 03:57 ET 2026-09-03 (Sonnet replay of the decision rows, Fable read; report `analysis/deep-research/BEAR-08-31-NO-TRIGGER-REPLAY.md`):** all 55 bear>=9 ticks (7 episodes, 09:46-13:40 ET, SPY in a $1.2 chop) had level_rejection + confluence + trendline_rejection TRUE and were refused by exactly ONE gate: blocker 8, the VIX floor (needs VIX > 17.30 AND rising; VIX sat 15.08-15.44 all day). 09-01: 60 such ticks / 12 episodes, again 100% blocker 8 (VIX 15.3-16.3). 09-02: 0. **Class D:** mechanically B (trigger fired, a ratified gate refused it), substantively C-leaning (shallow chop, no decisive rejection candle; the playbook's own prose says no puts below VIX 15). The setup is already demoted to OBSERVATION. So 08-31 was a GATE-SANCTIONED sit-out, not a detector gap -- the metric's `regressing` label on a fully gate-refused day is the defect (fix filed on AUTONOMY-METRIC-ZERO-ENTERS-08-31). Side finding: playbook VIX prose ('> 20 OR rising') does not match the coded gate ('> 17.30 AND rising') -- Saturday Rule-9 draft item 9. Blocker 8 is the same door the sole-blocker miner flagged RED tonight (106 events / 14 sessions): BEAR-F8-VIX-FLOOR-COSTING-REPLAY now has two whole sessions of refused events to price. :: status:done
  **CORRECTION 04:12 ET 2026-09-03 (Fable, ledger-checked):** '09-01 same shape' is wrong -- 09-01 had 13 ENTER_BEAR verdicts and 4 fills (the 60 refused ticks were morning-only). And since those entries happened with VIX ~16 (< 17.30), the blocker-8 rule as quoted in the report is incomplete -- read the gate's actual code before quoting the threshold again (UNVERIFIED which clause released it: rising-only branch, tier-conditional floor, or a different VIX source). Classification for 08-31 (gate-sanctioned) stands. Saturday item 9 must quote the CODE, not the report.
  **RULE SETTLED 04:30 ET -- see BLOCKER 8 AS CODED on BEAR-F8-VIX-FLOOR-COSTING-REPLAY.**

- [x] BATTERY-LOGIC-DUPLICATED-ACROSS-TOOLS (LOW, filed 2026-08-30 conductor self-audit triage) :: the G-battery pattern (G_mean/G_oos/G_drop3/G_bhfdr/G_n -- drop-topN, OOS split, BH-FDR, one-sample p, evidence-n floor) that adjudicates every gate-revalidation and knob-flip decision in this project is reimplemented inline, independently, in at least `backtest/autoresearch/daily_premium_budget_battery.py`, `backtest/tools/gate_revalidation_structure_veto_extended_2026_08_23.py`, and `backtest/tools/gate_revalidation_bearish_fill_bar_wholebook_2026_08_30.py` (plus likely more `backtest/tools/*` one-offs -- not fully enumerated this fire). No shared `backtest/lib/canonical_battery.py` exists. Risk is drift, not incorrectness observed so far (each copy currently agrees on thresholds) -- a future edit to one copy's drop-topN or BH-FDR alpha silently diverges from its siblings with no test to catch it. Bounded fix: `grep -rn "G_bhfdr\|G_drop3" backtest/` to enumerate every copy, extract one pure `run_g_battery(daily_deltas) -> dict` module, port each caller to it behind a byte-identical-output regression test (same inputs, same verdict, before/after), do NOT change any threshold while porting. :: depends:none :: status:pending
  **CLOSED (premise stale) 04:08 ET 2026-09-03 (Sonnet, Fable-verified 58 passed):** two of the three named files already delegate via `import gate_revalidation_ab as grab`; the third (`daily_premium_budget_battery.py`) implements the unrelated OP-11 battery (oos/wf/sub-window/anchor), not the G-battery. All four real G-battery producers pass `q=0.10` explicitly; drop_n=3 / n_floor=15 live inside the shared functions -- no threshold disagreement. The one real implementation moved to `backtest/lib/canonical_battery.py` (verbatim) with a `run_g_battery` wrapper; `gate_revalidation_ab.py` imports it, so every downstream `grab.*` caller is untouched. 12 new tests: byte-identical fixture regression, module identity, defaults, grep-guard on explicit `q=`. :: status:done
- [x] EVENING-TASK-MISSED-RUN-SWEEP (MED, filed 2026-08-26 conductor after fixing DRESS-REHEARSAL STALE) :: `Get-ScheduledTaskInfo` on all `Gamma_*` Ready tasks (2026-08-26 23:xx ET) showed ~15 evening-window tasks (roughly 17:00-22:00 MT trigger times) with `NumberOfMissedRuns` 1-3, same root cause as the DressRehearsal fix (commit `12f4a907`): J's box reboots most evenings in the 18:00-22:00 MT window (Kernel-Power event log), landing in single-daily-trigger windows. DressRehearsal was fixed (self_check-critical, RED). The other ~15 (FreeModelAudit, OosCheck, McpDailyAudit, RegimeShadow, GuardsFull, SpendSummary, WeeklyReview, BookEquityRefresh, GateRecency, EngineStressSwarm, ConductorWeekend, KitchenReviewer, AutoCommitCandidates, CryptoGrinderKeepalive, Prospector) were NOT individually triaged this fire (bounded scope) â€” check whether any are load-bearing enough to warrant the same "extra daily trigger slots + idempotent skip" pattern (see `markdown/infra/POWERSHELL-COMPAT.md` "Scheduled-task trigger permission envelope" for the mechanism â€” ONLOGON/ONSTART triggers are Access-Denied from this session's token, only extra DAILY slots work). Most are research/visibility-only and self-heal on the NEXT day regardless; only worth fixing the ones whose staleness has a real downstream cost. :: depends:none :: status:pending
  **CLOSED 03:41 ET 2026-09-03 (Sonnet, Fable-verified):** 15 evening tasks triaged. 5 already self-heal (EngineStressSwarm, KitchenReviewer, AutoCommitCandidates, CryptoGrinderKeepalive, Prospector), 2 adequately windowed (BookEquityRefresh, ConductorWeekend). **7 given `PT15M/PT30M` self-heal after an idempotence read of each script:** FreeModelAudit (dedupe by item_id), OosCheck (atomic per-row), McpDailyAudit (snapshot overwrite), RegimeShadow (dedupe by date; had 1 missed run), SpendSummary (replaces today's row), GateRecency (atomic snapshot), GuardsFull (`IgnoreNew` + 3600s timeout; the 08-31..09-02 dark task). Verified cold: GuardsFull/OosCheck XML `PT15M/PT30M`, State=Ready. WeeklyReview NOT windowed (an `Invoke-Claude` LLM call with no done-marker; a retry would double-bill ~$8) -- follow-up filed. `scheduled_task_staleness.py` already grades missed>=1 YELLOW / >=2 RED with the count (no change). 14 + 98 + 30 passed. Six re-registered tasks show UNKNOWN in staleness until their first fire tonight (history reset). :: status:done
  **REGRESSION + FIX 05:01 ET 2026-09-03 (Fable-caught via the fresh GuardsFull run; Sonnet fix, verified live):** re-running the install scripts to add the windows dragged three tasks BACK into the quiet blackout, because the 08-26 live re-timing was never propagated into the installers (OosCheck 18:30 MT, GateRecency 18:00 MT, FreeModelAudit 19:00 MT = 20:00-21:48 ET) -- `test_quiet_mode_starvation` went RED. Installers fixed to the registry's ET times and re-registered: OosCheck 21:40 MT, GateRecency Sun 21:35 MT, FreeModelAudit 21:48 MT, repetition kept, State=Ready (XML verified). New guard `test_install_script_times_match_registry_2026_09_03.py` parses 46 of 130 install scripts against the registry (84 unparseable/batch/dynamic, listed in its docstring) and RED-proofed. It also surfaced 9 more installers whose source is stale while their live trigger is correct (2 of the quiet-mode class: DressRehearsal, FuturesBrokerProbe; 7 older) -- allowlisted self-checkingly and filed INSTALL-SCRIPT-TIME-DRIFT-DORMANT-9. The builder's task chip was withdrawn (no chips). Lesson class: an install script is a second source of truth for a trigger; a live `Set-ScheduledTask` re-time MUST update the installer in the same commit (guarded now).

- [x] INSTALL-SCRIPT-TIME-DRIFT-DORMANT-9 (MED, scheduler hygiene, after-hours; filed 2026-09-03 05:01 ET) :: `test_install_script_times_match_registry_2026_09_03.py#KNOWN_PREEXISTING_MISMATCHES` lists 9 install scripts whose `-At` disagrees with the live trigger + registry (live is correct, installer stale): Gamma_DressRehearsal and Gamma_FuturesBrokerProbe would land inside the quiet blackout if their installer were ever re-run (same class as tonight's regression), plus 7 older drifts. Fix each installer's time to the registry value WITHOUT re-registering the task (or re-register only where the live trigger equals the registry already), remove the allowlist entries as they clear (the test fails on a stale entry, so the allowlist cannot rot), quote XML for any task touched. :: depends:none :: status:filed
  **CLOSED 06:03 ET 2026-09-03 (Sonnet, Fable-verified 51 passed):** all 9 installers corrected to the registry time WITHOUT re-registering (live == registry confirmed for 8 via Export-ScheduledTask; Gamma_ArchiveKeyLevels has no live task at all -- documented 'wired, not yet enabled'); allowlist emptied (left as a documented landing spot). DressRehearsal (23:44 ET) and FuturesBrokerProbe (23:05 ET) now land in the LOUD band if re-run. Anomaly noted, not touched: `Gamma_DressRehearsal`'s live XML carries THREE CalendarTriggers (21:44 primary + 19:00 MT + 23:15 MT debris from the 08-26 manual re-time) -- the two extra fire inside the quiet blackout and are wasted; clean-up = one `Set-ScheduledTask` after-hours with the installer's single trigger (filed below). :: status:done

- [x] DRESS-REHEARSAL-TRIGGER-DEBRIS (LOW, scheduler hygiene, after-hours; filed 2026-09-03 06:03 ET) :: `Gamma_DressRehearsal` has three CalendarTriggers live (21:44 MT primary = 23:44 ET, plus 19:00 MT and 23:15 MT debris from the 08-26 manual re-time); the debris triggers fall inside the 18:00-23:00 ET blackout and are disabled/wasted. Re-register from `setup/install-dress-rehearsal.ps1` (now correct at 21:44 MT) after 16:00 ET, quote the XML showing a single trigger with PT15M/PT30M, State=Ready. :: depends:none :: status:done -- CLOSED 18:34 ET 2026-09-03: re-registered from setup/install-dress-rehearsal.ps1; export after = exactly ONE CalendarTrigger 21:44 MT (23:44 ET) daily, State=Ready, NextRunTime tonight; the drifted action (stray --env PYTHONPATH, system pythonw) normalized to the installer's venv form and the task flipped Enabled false->true. Correction to the filing: the installer sets NO PT15M/PT30M repetition on this nightly single-shot and the guards agree (15 passed) -- the filing's expectation was wrong, not the installer.

- [x] WEEKLY-REVIEW-RETRY-DONE-MARKER (LOW, filed 2026-09-03 03:41 ET from EVENING-TASK-MISSED-RUN-SWEEP) :: `Gamma_WeeklyReview` is the one evening producer left without a self-heal window because its script is an `Invoke-Claude` LLM call (~$8/run, 12-min cap) with no same-week done-marker, so a retry within the window would double-bill. Add a done-marker (write `automation/state/weekly-review-done.json` with week_iso + generated_et on success; skip when present for the current ISO week), test it, then give the task the `PT15M/PT30M` window via its install script and quote the XML. :: depends:none :: status:filed
  **CLOSED 04:22 ET 2026-09-03 (Sonnet, Fable-verified):** `setup/scripts/weekly_review_marker.py` check/write; `run-weekly-review.ps1` gates `Invoke-Claude` behind `check` (SKIP already-done <week> when `weekly-review-done.json` carries the current ISO week) and writes the marker only in the exit-0 branch, so a failed run leaves no marker and the retry window can recover it. First install script for the task (`setup/install-weekly-review.ps1`); re-registered Sunday 21:12 MT with `PT15M/PT30M` (XML verified: rep PT15M/PT30M, State=Ready). LLM never invoked. 16 + 14 passed. :: status:done
- [ ] TP1-R50-FORWARD-SHADOW (HIGH, filed 2026-08-23 Opus adjudication, supersedes TP1-R50-READJUDICATION which is DONE) :: R_tp100_f50 re-adjudicated on extended popA (n=213, commit 97f3c864): STILL fails G4, DO_NOT_ARM stands. The failure is STRUCTURAL not statistical -- 2025H1 (n_changed=4) and 2026Q1 (n_changed=4) are CLOSED calendar windows, forward extension only grows the newest window, so at most 2 of 4 windows can EVER qualify against G4's >=3 requirement. G4 is unreachable for this cell by construction. But the cell's profile is otherwise strong: 7/8 gates pass, ALL FOUR windows positive (+228.95/+333.20/+253.20/+151.95), runner_anchor +$628.05 (the prereg's declared operative veto, POSITIVE), p=0.002617, sole BH survivor of 28 cells; live-arm proxy weakly supportive (+$1,050 on n=25 shared signals). â›” DO NOT re-spec G4 to let it pass -- rewriting a gate after seeing which cell it blocked is forking-paths and the prereg says the bar is not softened. â›” DO NOT write a new backtest prereg on the SAME data -- we have already seen the answer, that population is contaminated. THE ONLY CLEAN PATH: build a forward counterfactual SHADOW instrument following the established stop_mode / day-throttle shadow pattern (nightly per-trade delta of f0.5 vs live f0.667 at the +100% TP1, written to analysis/recommendations/, with a PRE-REGISTERED forward bar: n_days and a decision rule frozen BEFORE any data accrues). Judge on forward data nobody has seen. :: depends:none :: status:pending
  **SHADOW RUNNING 04:49 ET 2026-09-03 (Sonnet, Fable-verified 33 passed):** `setup/scripts/tp1_r50_forward_shadow.py` -- nightly per-trade delta of an f=0.5 TP1 sell vs the live f=0.667, from recorded broker legs only (`fills-ledger.jsonl`): qty_moved = int(qty*0.667) - int(qty*0.5) (mirrors `ExitState.from_entry`'s int-floor split, cross-checked qty 3-20), delta = qty_moved x (runner_avg - tp1_price) x multiplier; single-leg closes = never-reached-TP1 ($0, counted apart from no_op_rounding). Live fraction confirmed 0.667 on every SPY arm via `strategies.by_name('ribbon_ride')` + `accounts.json` patches (drift -> row skipped, never silently included). Prereg `prereg-tp1-r50-forward-shadow-2026-09-03.md` (structured build_step): bar = days_accrued >= 20 AND n_tp1_reached >= 25; ship-candidate only if day-clustered CI-lower > 0 AND top-3 share < 50% AND ex-best-day sum > 0; not softenable. Ledger/summary under `analysis/recommendations/tp1-r50-forward-shadow-*`; accrual starts today, nothing backfilled. `Gamma_Tp1R50ForwardShadow` 16:40 ET weekdays PT15M/PT30M, State=Ready, real fire rc=0; registry 158 -> 159. Dry run: `n_trades:0, status:ARMED_AWAITING_FILLS`. :: status:shadow-running
- [x] GATE-DESIGN-FIXED-CALENDAR-WINDOWS-STARVE-LOW-FIRE-RATE-KNOBS (MEDIUM, filed 2026-08-23 Opus adjudication) :: FORWARD-ONLY doctrine item -- â›” must NEVER be applied retroactively to any already-frozen prereg. G4-style sub-window stability gates split the population into FIXED CALENDAR windows and require >=N windows to hold >=5 changed trades. For a low-fire-rate knob (R_tp100_f50 fires on 20.4% of trades) the older windows are permanently starved and the gate becomes unreachable regardless of how much forward data accrues -- it stops measuring stability and starts measuring "did your knob fire often enough in a fixed past period". Proposed alternative for FUTURE preregs: split into equal-CHANGED-TRADE-COUNT buckets (e.g. 4 buckets of equal n_changed) so each bucket has adequate power, testing the same stability property. Write the decision into the ratification rules / BACKTESTING-PLAYBOOK so future preregs pick the right window scheme UP FRONT. Worked example to cite: analysis/recommendations/tp1-r50-readjudication-2026-08-23.json. :: depends:none :: status:pending
  **CLOSED (doctrine written, forward-only) 04:28 ET 2026-09-03 (Sonnet, Fable-verified):** BACKTESTING-PLAYBOOK §4.5 now says a NEW prereg picks its window scheme up front and records it: expected changed-trade fraction < 33% -> equal-changed-count buckets (`canonical_battery.equal_count_buckets`, 7 tests incl. the R_tp100_f50 worked example where 4+13+4+14 calendar windows fail the >=5 floor and 4 equal buckets clear it), else calendar windows; never changed after data is seen; never applied retroactively to a frozen prereg. :: status:done
- [x] WATCHER-LANE-PROVENANCE-AUDIT (HIGH, filed 2026-08-23 Fable profitability sweep) :: Non-ribbon watcher setups (VWAP_CONTINUATION âˆ’$1,469.94 n=46; BOLLINGER_SQUEEZE / VIX_REGIME_DAYSIDE / VWAP_RECLAIM_FAILED_BREAK) net âˆ’$2,139.38 = 110% of the book's whole 303-trip deficit, at the same WR as ribbon â€” and per the TP1 prereg's own words are "trading live with no validation on the only deep population this project owns" (popA is ribbon-only). NOT a P&L block (dropping-the-lane-as-filter already REFUTED â€” 64% one day). This is gate-provenance doctrine (J 2026-07-02: every armed gate/lane needs provenance+evidence or dies): locate the ratification record that armed each watcher family; any family with NO record moves to SHADOW pending its own prereg'd validation. :: depends:none :: status:pending
  **CLOSED 2026-09-03 03:06 ET (Fable overnight loop, tick only -- work was done 2026-09-02, see OPUS-WORK-ORDER-2026-09.md:273):** the work order recorded this DONE on 09-02; the queue box was never flipped. No new work tonight; status reconciled so Friday's synthesis does not re-open it. :: status:done
- [x] SSR-FUNDABILITY-MEASURES-NOTIONAL-NOT-MARGIN (MEDIUM, filed 2026-08-23 Opus adjudication) :: The ssr-v2 respec (commit 77442e70) cut worst-case notional from ~$3.17M (1,584x equity) to ~$316,553 (158.3x) against the real $2,000 account (automation/state/futures/account.json, acct 5WW73759). But notional/equity is the WRONG METRIC for futures -- you never post notional, you post MARGIN. The binding constraint is day-trade margin AND overnight/initial margin per contract (micros are roughly $50-150/contract day, materially higher overnight; broker-specific). At 158x notional the fundability gauge reads scary-but-passing while the question that actually decides whether this lane can trade -- can a $2,000 account carry qty=3 MNQ + qty=3 MGC, and can it carry them OVERNIGHT -- is never asked. SSR holds positions across sessions (it books round trips, not scalps), so overnight margin is very likely the real gate and $2,000 may still not fund it. FIX: replace/augment `_fundability` with a margin-based check sourced from the broker's actual requirements (tastytrade sandbox exposes margin fields; use them, do not hardcode), and state day vs overnight separately. Until then treat "fundability GREEN" as unproven. :: depends:none :: status:pending
  **CLOSED (instrument shipped, reads UNPROVEN) 04:40 ET 2026-09-03 (Sonnet, Fable-verified 10 passed):** `setup/scripts/ssr_margin_check.py` (GET-only) reads the broker's own `Account.get_margin_requirements` per symbol and writes `automation/state/futures/ssr-fundability.json` {as_of, per_symbol day/overnight, qty, equity, day_ok, overnight_ok, gauge}; GREEN only when overnight_ok. Tonight the sandbox 502'd the margin-requirements endpoint 3/3 and its account aggregate shows $17,107 intraday/overnight margin while FLAT (stale snapshot), so per-symbol MNQ/MGC = DATA_MISSING and the gauge reads **UNPROVEN** (never GREEN by omission). Re-run when the endpoint answers or the account holds qty. Notional/equity is no longer the fundability metric. :: status:done
- [x] SSR-REAL-BLOCKER-IS-EXIT-QUALITY-NOT-SIZING (MEDIUM, filed 2026-08-23 Opus adjudication) :: âš ï¸ Do not mistake the ssr-v2 respec for progress on the actual failure. SSR-v1 reached n=17 round trips with positive absolute expectancy (+$27,335.69) but FAILED beats_null: an unmanaged hold to the same closing bar returned MORE (+$30,828.09). The managed exits SUBTRACT value. Contract size has zero bearing on that -- v2 restarts the clock at n=0 on IDENTICAL exit logic, so absent an exit change the most likely outcome is reproducing the same beats_null failure 20 round trips later. Before spending another forward clock: diagnose WHY the managed exits lose to hold (exit too early on winners? stop placement? time-based exit cutting the right tail?), the same way the 0DTE lane's exit-stage P&L was decomposed. An arming bar that cannot be cleared by accruing more data is not a clock, it is a stall. :: depends:none :: status:pending
  **DIAGNOSED 04:40 ET 2026-09-03 (Sonnet, Fable read; `analysis/deep-research/SSR-EXIT-QUALITY-DECOMPOSITION-2026-09-03.md`):** reproduced n=17 to the cent ($27,335.69 managed vs $30,828.09 held; ledger now n=18, gap -$5,336). Shortfall by exit class: **runner/trail exits cut winners early = 4 trades, -$9,839, 83%** of gross downside; stops hit then reversed = 3 trades, -$2,020 (17%); time-exit cutting the right tail = 0 (5 of 6 time exits equal the null by construction); 10 trades matched or beat the null (+$8,366). One-sentence candidate for a v2 prereg (NOT implemented): replace the runner leg's fixed profit cap (nearest opposing level beyond TP1, else 3R capped at 5R) with a trailing stop or an 8-10R cap. Arming stays blocked until an exit prereg is run; sizing was never the blocker. :: status:diagnosed
  **V2 EXIT PREREG FILED 04:47 ET 2026-09-03:** `analysis/recommendations/prereg-ssr-v2-runner-exit-2026-09-03.md` -- current rule quoted (`ssr_shadow._pick_runner` L468-490: nearest opposing level beyond TP1 else 3R, capped 5R; TP1 1.5R for 2 of 3); cells = chandelier trail k x ATR14 (k 2/3/4) and wide cap 8R/10R; FRESH forward clock >= 20 new round trips after 04:47 ET today AND >= 40 sessions (the existing 16 v2 trips are excluded -- and they already reproduce the failure live: total -$4,528 vs null -$3,341, beats_null false per `ssr-shadow-progress.json` 04:30 ET); ship rule beats_null CI-lower > 0 AND drop-top-2 >= 0; fundability must ALSO read GREEN (currently UNPROVEN) before arming; `build_step` names `setup/scripts/ssr_shadow_runner_variant_2026_09_03.py::compute_variant_round_trips` writing a separate ledger. Sizing explicitly a red herring. :: status:prereg-filed
- [~] MULTI-SIGNAL-PORT-BUILD-SHARED-SIGNAL (DEFERRED 2026-08-23 by Opus adjudication -- do NOT pick this up until the gating condition below is met) :: â›” DEFERRAL REASON, and it is a premise failure not a priority call: this item's whole rationale was "the production SPY signal is the real edge (58.23% hit, +4.89 sigma @ +10min) -- port it symbol-generic and it may transfer." But the SAME evening's adjudications established that the SPY engine ITSELF is not currently profitable: book -$1,940.98 over 303 round trips / 35 sessions, WR 23.10% vs 25.24% breakeven, and EVERY entry-side lever tested came back negative, already-closed, or non-existent (structure_veto, require_bearish_fill_bar, conviction ladder, watcher families, and direction itself). Porting a signal from an unprofitable engine onto ~72 more names does not create edge -- it spreads the same deficit across more symbols and more spread cost, while consuming the one scarce resource (adjudication attention) that the profitable-making work needs. A directional hit-rate that beats a null at +10min is NOT the same thing as a profitable engine; that gap is precisely what tonight measured. GATING CONDITION to un-defer: SPY 0DTE shows positive expectancy on real fills over a window that survives drop-top3 AND drop-best-2-days (i.e. a profit that is not concentration-carried). Until then this stays deferred. The harness (backtest/tools/multi_intraday_null_harness.py) and the symbol-generic infra survive and adjudicate any future signal in one session -- nothing is lost by waiting. Original text :: The one untested hypothesis left for the multi-symbol/weekly sector after levels-transplant + filter-stack were both ruled out: port automation's production build_shared_signal.py (the actual 58.23%/+4.89Ïƒ@+10min signal, zero SPY literals but reads SPY-specific state files) to take a symbol argument, run it through the RETAINED null harness (backtest/tools/multi_intraday_null_harness.py) under a FRESH pre-registration with a hit-rate/right-tail channel alongside mean-return (per SPY-CALIBRATION doc's own recommendation). Banned per post-mortem: threshold sweep, more names, re-slice. :: depends:none :: status:pending
- [x] EXIT-COUNTERFACTUAL-BACKFILL-DATA-PREREG (MEDIUM, filed 2026-08-23 after the exit study was REFUTED) :: The exit-policy question could not be tested because `cf_time_stop_pnl` is a DEAD SCHEMA COLUMN -- 3 of 508 rows populated, 0 of 493 in-window; both writers (setup/scripts/fleet_journal_bridge.py:671, backtest/autoresearch/webull_winner_journal.py:414) emit the literal empty string; nothing has ever computed it. Where populated it is also untrustworthy (1 row has cf_time_stop == dollar_pnl exactly; 1 has cf_high_water < cf_time_stop, impossible for a high-water bound). â›” Do NOT write another exit-INTERVENTION prereg -- the hypothesis was refuted on every computable cut (see PROFITABILITY-ORDER-2026-08-23.md Â§5). Write a DATA prereg instead, freezing this question: backfill from OPRA minute bars at POSITION level (NOT per exit leg -- 124 of 250 in-window positions exited in more than one piece, which is exactly why the column was never computable), with the null defined as TRULY unmanaged (no premium cap -- the -50% cap is graveyarded validated-KEEP and must not sit inside the null; on identical rows no_stop_ride +$22.86 vs wide_stop_-50 +$65.40 vs hold_to_time +$79.03 per trade, a 3.5x spread driven entirely by which intervention leaked into the "null"), and with `stop_mode` sourced from the decisions ledger so G6's Simpson's-paradox stratification becomes computable (neither trades.csv nor analysis/autopsies/ carries stop_mode today). Only after >=80% coverage exists is the beats_null question answerable. :: depends:none :: status:pending
  **DATA PREREG WRITTEN 04:38 ET 2026-09-03 (Sonnet, Fable read):** `analysis/recommendations/prereg-exit-counterfactual-backfill-data-2026-09-03.md` -- position-level OPRA backfill (124/250 in-window positions exited in pieces), null = truly unmanaged hold-to-time with NO stop evaluated at all (the existing `trade_autopsy.COUNTERFACTUALS['hold_to_time']` still carries premium_stop_pct -0.95 and is NOT a null -- caught and excluded), `stop_mode` from the decisions ledger via the existing `pain_ledger` recovery, coverage bar >= 80% before any question, frozen question list, structured `build_step` naming `backtest/tools/exit_counterfactual_backfill_2026_09_03.py` (does not exist yet). The two dead-column writers re-verified: `fleet_journal_bridge.py:671-672` and `webull_winner_journal.py:414-415` still emit empty strings. Build is a Sunday-class job (OPRA fetch). :: status:prereg-filed
- [x] LOSS-MAGNITUDE-AND-SIZING-IS-THE-UNTESTED-AXIS (HIGH, filed 2026-08-23 Opus adjudication, THREAD not finding) :: Surfaced by the two-tailed concentration fix (0a51b817): BOTH direction labels are concentration artifacts in OPPOSITE tails -- bear -$16.71/tr flips to +$397 at drop-worst3; bull +$2.45/tr flips to -$1,455 at drop-top3. So the deficit is NOT a broad bleed, it is carried by a handful of extreme trades. Only three levers can attack loss magnitude: (a) don't take them = entry selection, EXHAUSTED (every lever adjudicated negative 2026-08-23); (b) cut them sooner = stop tightening, SETTLED DEAD (0/34 cells, destroys $3,034.88 of eventual winners); (c) SIZE THEM SMALLER = never tested on this book. Doctrine already points at (c): C31/L168/L203 -- J's 667 real trades were +$4,576 at 1-2 lots vs -$17,461 at 3+ lots, recoverable money was the no-add + catastrophe-cap PACKAGE. Live per-trade caps are 30% of equity (Safe) / 50% (Bold); the -50% catastrophe cap is validated and bounds the PERCENTAGE, but NOTHING bounds the DOLLARS. âš ï¸ This is a re-reading of two concentration numbers with NO null test -- and sizing is the single easiest way to manufacture a backtest illusion (shrink size, shrink variance, flatter Sharpe, same broken edge). It needs its own FROZEN prereg with a dollar-denominated loss-cap cell and a right-tail-damage gate BEFORE anyone runs a sweep. Do not tune sizing knobs looking for a good number. :: depends:none :: status:pending
  **FROZEN PREREG FILED 04:44 ET 2026-09-03 (Sonnet draft, Fable read):** `analysis/recommendations/prereg-loss-magnitude-dollar-cap-2026-09-03.md`. What is already live and NOT re-tested: `daily_loss_kill_switch_dollars` $400 (a daily stop), `max_contracts_per_entry` 3-5 + `max_position_dollars` $1,000 via `risk_gate.cap_entry_qty` (clamps down only), the -50% catastrophe cap (a % bound, ~$500 on a $1,000 position). The untested gap: an independent per-position DOLLAR loss cap below that. Cells: CONTROL (~$500 live-equivalent) / $350 / $250, sizing scaled DOWN only with `cap_entry_qty`'s exact floor-division rounding and its SKIP-below-min_contracts rule reused verbatim. Population: core arms 07-08..09-02 (safe-2 n=90, bold-2 n=42 per the gate; window equality flagged UNVERIFIED for the build step to re-derive), equal-count buckets per playbook §4.5. Right-tail-damage gate: top-3-winner shrinkage < bottom-3-loser shrinkage AND ex-best-day expectancy not lower AND PF CI-lower not lower; Sharpe/variance disclosure-only (illusion guard). Winning cell must then clear the same gates on a fresh >= 20-day forward shadow. Vocabulary SHIP-CANDIDATE / SHADOW-PENDING / REFUTED / UNDERPOWERED. `build_step` names `backtest/tools/loss_magnitude_dollar_cap_sweep_2026_09_03.py::run_dollar_cap_sweep` (not built). Nothing before 10-30, and only as a tightening. :: status:prereg-filed
  **QUEUE-TERMINAL 2026-09-03 05:10 ET (Fable):** the queue's job on this item is done (prereg filed / diagnosis recorded / superseded by a filed follow-up); the living clock is the prereg file or the successor item, not this box. :: status:done
- [x] PLANNED-STOP-IS-NOT-THE-EXECUTED-STOP (HIGH, filed 2026-08-23 Opus adjudication, surfaced by the bear-side sweep) :: DATA-INTEGRITY defect that silently invalidates any study keying on planned_stop: in **122 of 154** premium_stop exits (79%) the ledger's `planned_stop` does NOT match the stop that actually fired. Measured while refuting the "bear stops fire at -8% vs bull -43%" claim -- the actually-fired stops are -7.0% bear vs -7.4% bull (no asymmetry), but the PLANNED values told a completely different story. Any past or future analysis that reads planned_stop as the realized stop is wrong by default at a 79% rate. FIX: (1) find why they diverge (stop moved after entry? chandelier ratchet not written back? render-vs-armed divergence, the same class as the 2026-08-06 D4 TP1 display bug?); (2) record the EXECUTED stop explicitly as its own field so the two can never be conflated; (3) guard test. Also sweep analysis/ for existing studies that used planned_stop and flag them. :: depends:none :: status:pending
- [x] MONITORING-INSTRUMENTS-LACK-CONCENTRATION-GUARDS (MED, downgraded from HIGH 2026-08-27 -- core risk retired, residual scope is a hygiene sweep, filed 2026-08-23 Opus adjudication) :: SYSTEMIC, three confirmed instances in ONE weekend, all the same shape -- a monitoring instrument computes a verdict from a raw mean over a small sample with no concentration term, so a couple of outlier trades/days flip the label: (1) gate_expiry_check.py::costing_verdict false-RED on structure_veto_enabled; (2) same on require_bearish_fill_bar; (3) core_strategy_recency.py stamping BULL GREEN on a 2-day fluke (2,767% of net from 2 days) and BEAR RED on an evenly-spread bleed with a HIGHER win rate -- which triggered a 13-agent investigation into a mechanism that does not exist. Cost of the class: two full G-batteries + one multi-agent sweep, all to disprove labels that were never evidence. (1) and (2) fixed in 71c39545; (3) + a shared backtest/lib/concentration.py helper dispatched 2026-08-23. **PARTIAL 2026-08-26 conductor AFTERHOURS (05:30 fire, commit pending): live_readiness.py DONE** -- the CLAUDE.md "Live threshold" gate (the instrument named explicitly in this item's own candidate list, and arguably the highest-stakes one since a PASS there is the evidence base for a live-money conversation with J) now runs the same trade-level drop-top3 term via `lib.concentration.drop_top_n` (reused, not reimplemented): an otherwise-clean PASS on the 4 CLAUDE.md criteria downgrades to `PASS_CONCENTRATED` when the positive expectancy does not survive dropping the arm's top-3 winning trades. Downgrade-only (never upgrades FAIL/UNKNOWN/INSUFFICIENT); `_book_wide_rollup` counts `arms_pass_concentrated` on its own key rather than folding it into `arms_pass`. 5 new guard tests (concentration-downgrades-pass, concentration-survives-stays-plain-pass, concentration-never-upgrades-a-fail, book-wide-rollup-counts-separately, plus the existing 18 re-verified) -- 23/23 pass; RED-proofed via `git stash` (3 new tests correctly KeyError pre-fix, 23/23 pass post-fix). Curated safety gate 59/59 PASS. Live smoke run against the real ledger: zero behavior change today (all 5 arms currently read UNKNOWN off unattributed rule-breaks, which short-circuits before the concentration term is even consulted) -- this is a forward-looking correction, not a live verdict flip. **REMAINING WORK, still open:** desk_allocator.py scoring, chop meter, ladder-rung tally, entry-quality scorers, shadow-tally/summary writers under analysis/recommendations/*-shadow-summary.json, and the general *_verdict/*_check.py sweep across setup/scripts + backtest/autoresearch -- none of those audited yet. Doctrine-encode step (BACKTESTING-PLAYBOOK: "a mean without a drop-topN is not a verdict") also still open.

**AUDIT PASS 2026-08-27 05:30 ET conductor AFTERHOURS (this fire, doc-only, no code change) -- all 5 named candidates checked, ZERO additional defects found.** Read each producer's actual verdict/score logic, not its name: `desk_allocator.py::assess_spy/assess_futures` -- NOT susceptible, its own docstring states "DELIBERATELY NOT SCORED: P&L level," it ranks progress/broken/dead-signal flags and only prints P&L as informational headline text, never gates a decision on it. `chop_exposure_meter.py` -- NOT susceptible, its own docstring states "the meter measures exposure; it does not judge" -- measurement-only, no PASS/FAIL emitted anywhere. `day_throttle_shadow.py` / `stop_mode_shadow_ledger.py` (the two real producers behind "shadow-tally/summary writers") -- NOT susceptible, both emit `verdict_ready` (an n>=threshold readiness flag) not a PASS/FAIL judgment from a mean. `entry_quality_ledger.py` -- NOT susceptible, ALREADY gates its verdict (`FORWARD_SHADOW_CANDIDATE`/`WATCH`/`REJECT`) on `delta_drop_top2 > 0` (G3), not a bare mean. `score_ladder_shadow_nightly.py`'s frozen forward-arm bar -- NOT susceptible, the prereg criterion already requires (b) no single session worse than -$500 AND (c) chop-day average not worse than -$300, alongside the mean -- a tail-risk term was already baked in at freeze time (2026-08-07), predating this lesson by 16 days but structurally equivalent to one. Spot-checked 7 more `*verdict*`/`*_check(` producers found via `grep -l` sweep of setup/scripts (`gate_recency_report.py`, `oos_check_runner.py`, `regime_attribution.py` [already has its own named `concentration()` function], `risky1_lane_composition_check.py`, `exit_policy_beats_null_2026_08_23.py` [two-tailed drop-top3/drop-worst3 already first-class per its own docstring], `bold_tier_rail.py`, `trendline_tier_rail.py`) -- zero bare-`fmean`-without-concentration hits. **Doctrine-encode step DONE:** folded a generalized paragraph into `markdown/research/BACKTESTING-PLAYBOOK.md` Â§4.3 (Concentration gate) stating the rule applies to ANY verdict-producing function repo-wide, not just backtest strategy evaluators, naming the shared `backtest/lib/concentration.py::drop_top_n` helper and all 3 real incidents + all 5 audited-clear candidates as the reference list -- so the next new `*_verdict`/`*_check.py` author greps doctrine before writing a bare-mean gate. **Not exhaustive:** 14 of the 21 `*verdict*`/`*_check(`-matching files in setup/scripts were not individually opened this fire (`heartbeat_core.py`, `monday_verify.py`, `kitchen_reviewer.py`, `engine_health.py`, `firm_brief.py`, `crypto_twin_core.py`, `autonomy_report.py`, `task_state_guard.py`, `crypto_twin_ladder_sim.py`, `crypto_twin_scenarios.py`, `participation_daily.py`, `free_model_audit_prospector.py`, `twin_gauntlet_conductor_hook.py`, `free_model_audit_twin_review.py`) nor was `backtest/autoresearch/` swept at all -- downgrading item from HIGH to MED and re-scoping it explicitly to that residual list rather than closing, since a genuine sweep of ~35+ files is not a single bounded fire. :: depends:none :: status:pending
  **CLOSED (audit, no gap) 04:08 ET 2026-09-03 (Sonnet):** `lib/concentration.drop_top_n` is shared; `core_strategy_recency._concentration_survives` gates GREEN/RED with drop-top3/bottom3 per trade and best2/worst2 per day (downgrade-only, fail-closed); `live_readiness` done 08-26; `entry_quality_ledger` (G3 drop-top2), `vix_floor_shadow` (sub_window_stable), day-throttle / loss-armed shadows (ex-best-session deltas, no bare verdict) all carry a concentration term; `desk_allocator`, `chop_exposure_meter`, ladder tools stamp no mean-derived verdict. Remaining GREEN/RED hits are liveness checks or one-off R&D scripts. The item's 'remaining work' list was stale. :: status:done
- [x] VWAP-KILLCHECK-PREREG-DEADLOCKED (MEDIUM, filed 2026-08-23 Opus adjudication) :: analysis/recommendations/vwap-family-killcheck-prereg-2026-08-18.json is UNRESOLVABLE BY CONSTRUCTION: it requires 20 live sessions or n>=25 forward positions from vwap_continuation, but that strategy was disarmed 2026-07-25 (fleet leak closed 08-12) -- six days BEFORE the prereg was frozen -- and has taken zero fills since. A forward clock that cannot tick is a dead instrument masquerading as evidence-in-progress. Resolve it: either formally PARK it with a written verdict (preferred -- the strategy is already disarmed, so the kill question is moot) or re-specify its resolution path to something achievable. Do not leave it accruing. Sweep for sibling preregs with the same shape (forward clock on a disarmed/dark producer). :: depends:none :: status:pending
  **PARKED 04:38 ET 2026-09-03 (Sonnet, Fable-verified):** `vwap-family-killcheck-prereg-2026-08-18.json` status -> `RETIRED_UNRUNNABLE_AS_FROZEN -- not a verdict on the hypothesis` (the terminal form `prereg_hygiene.py` recognises; same precedent as the level-memory prereg), dated `parked_reason`, `reopen_condition: vwap_continuation re-armed on any arm`; frozen fields untouched; no hash pin references this file. Sibling sweep against `params.json#extra_setup_exec_armed`: four setups are dark (vwap_continuation, vix_regime_dayside 07-25; vwap_reclaim_failed_break, bollinger_squeeze 08-24) but only this prereg is scoped solely to a dark producer -- the five other files that mention them are book-wide studies whose clocks tick through live arms; nothing else parked. Hygiene before/after: 128 files, 4 flagged, 19 result-stale, unchanged. :: status:parked
- [x] NO-DEEP-POPULATION-FOR-NON-RIBBON-FAMILIES (MEDIUM, filed 2026-08-23 Opus adjudication) :: Structural evidence gap, confirmed by the watcher-lane provenance audit: popA (391-day, n=191) is ribbon-family ONLY, and prereg-tp1-reachability states it outright ("popA cannot test vwap... ineligible to ship REGARDLESS of gates"). So EVERY non-ribbon family (bollinger_squeeze excepted -- it has its own 373-day grind) is structurally limited to n=76-153 one-off real-fills studies and can never clear a population-scale bar. Decide the doctrine: (a) build a non-ribbon deep population, or (b) formally hold non-ribbon families to a FORWARD-CLOCK standard instead of a population standard, and write that into the ratification rules so future families aren't ratified on thin evidence by default. Concrete live case: VWAP_RECLAIM_FAILED_BREAK is armed on 4 arms with n=76 backtest evidence and live WR 12.5% (n=8) vs 55.3% backtest -- n=8 is too small to act on, so it needs a forward clock, NOT a disarm. :: depends:none :: status:pending
  **CLOSED (decision b, doctrine written) 04:28 ET 2026-09-03 (Fable):** BACKTESTING-PLAYBOOK §4.9 -- a family without a deep population is ratified only on a pre-registered FORWARD CLOCK (frozen n_days / n_positions + decision rule before data accrues, per the stop-mode / day-throttle shadow pattern); backtest-only evidence for such a family is disclosure, never a ship bar. Live case named: VWAP_RECLAIM_FAILED_BREAK (4 arms, n=76 backtest, live n=8) needs a forward clock, not a disarm. Cross-links verified (`prereg-tp1-reachability-2026-08-06.json`, the shadow ledgers). :: status:done

- [x] FUTURES-EOD-PERSONA-STALE-PATHS (LOW, filed 2026-08-23 after commit 46311b7f) :: futures-eod.md Step 4's hand-written CSV schema was the live data-loss bug (fixed 46311b7f: persona now calls code-owned record_trade(); 3 destroyed 08-10 rows backfilled; guard backtest/tests/test_futures_journal_schema_guard.py). Steps 0/1 of the same prompt still reference stale architecture (position.json, account.json, old TastytradeBroker import path) â€” audit those against the current trader/ state layout and fix or delete; same persona-drifts-from-code class (C7/C14). :: depends:none :: status:pending
  **CLOSED 03:43 ET 2026-09-03 (Sonnet):** `automation/prompts/futures-eod.md` Steps 0/1 rewritten: the `futures/{position,account,risk}.json` trio has been frozen since 2026-06-17 (MNQ era, no current reader/writer); would-be ledger lives at `futures/trader/would-be-trades.jsonl`; no current `-heartbeat.jsonl` writer; import convention corrected. Now points at `health.json`, `trader-broker/`, `trader/last-tick.json`, `decisions.jsonl`, with a dated note. :: status:done

- [ ] KALSHI-RTH-LIQUIDITY-RERUN (LOW-MEDIUM, filed 2026-08-23 Fable profitability sweep) :: $0 unblock: re-run research/kalshi/kalshi_liquidity_survey.py during weekday RTH â€” the 34â€“36Â¢ index-series spread reading that blocks the lane was a Sunday quote-starved sample. If KXINXU/KXINX clear the 5Â¢ gate at RTH, THEN ask J for the API key (the only J-step); if not, retarget to the BTC daily series (1â€“2Â¢ spreads) or leave shadow. Also: no scheduled task was ever registered for the shadow ticker â€” register one or formally park the lane. :: depends:none :: status:scheduled
  **SCHEDULED 03:56 ET 2026-09-03 (Sonnet):** confirmed `research/kalshi/kalshi_liquidity_survey.py` needs no API key (public GET `/markets` + `/markets/{ticker}/orderbook` on `api.elections.kalshi.com`, no Authorization header anywhere in `_get()`). Added `--out` (default `analysis/kalshi/liquidity-survey-<ET date>.json`, was a single overwritten file) and one `5C-GATE: <SERIES>=PASS/FAIL(Xc)` summary line per series. Registered `Gamma_KalshiLiquiditySurvey` (`setup/scripts/install-kalshi-liquidity-survey.ps1`): two weekly Mon-Fri `CalendarTrigger`s at 10:30 ET + 14:30 ET, each `PT15M`/`PT30M` self-heal repetition (not a one-shot trigger) â€” `Get-ScheduledTask` confirms `State=Ready`, `Export-ScheduledTask` XML confirms both triggers. Off-hours dry run (03:53 ET, pre-market, NOT RTH â€” labeled as such): `5C-GATE: KXINXU=FAIL(71.5c) KXINX=NO-DATA ... KXHIGHNY=PASS(5.0c) ... KXNFLGAME=PASS(2.0c)` â€” confirms the pipeline works; KXINXU/KXINX's real RTH verdict is still open. **Decision rule (lives in the script's own module docstring):** 3 consecutive weekday-RTH passes on the 5c gate for KXINXU/KXINX â†’ ask J for the Kalshi API key; otherwise retarget the shadow lane to the BTC daily series (KXBTCD/KXETHD) or formally park it. Second half of this item ("register or park the shadow ticker") is answered by registering the measurement task â€” park/key decision is deferred to the accumulated evidence, not decided here. Full detail: `automation/state/SCHEDULED-TASKS.md` Active table, `Gamma_KalshiLiquiditySurvey` row.
  **SCHEDULED 03:58 ET 2026-09-03 (Sonnet, Fable-verified):** the survey needs NO key (public `/markets` + `/orderbook` reads only). `kalshi_liquidity_survey.py` gained `--out` (dated file under `analysis/kalshi/`) and a `5C-GATE:` summary line; `Gamma_KalshiLiquiditySurvey` registered weekdays 10:30 + 14:30 ET (both triggers `PT15M/PT30M` self-heal, State=Ready; registry 156 -> 157; 14 guard tests passed). Off-hours dry run 03:53 ET (quote-starved, labelled): KXINXU FAIL(71.5c), KXINX NO-DATA, KXBTCD FAIL(31c), only the weather/NFL series pass 5c. **Decision rule (in the module docstring):** KXINXU/KXINX clear 5c at RTH on 3 consecutive weekdays -> ask J for the key; else retarget to the BTC daily series or park. First RTH reading lands today 10:30 ET. :: status:scheduled

- [ ] FABLE-ESCALATION-RISKY1-SEQUENCE-REJECTION-PARITY-GAP (HIGH, filed 2026-08-23 conductor-weekend AFTERHOURS, root-caused NOT fixed -- touches a LIVE fleet arm's entry-quality classification, needs top-tier judgment before any code change) :: **What broke:** `pytest backtest/tests/test_replay_fleet_arms.py` has 2 REDs found (not caused) by J's 2026-08-21 20:42 triage session (commit `119bc54e`'s own list: "test_replay_fleet_arms (2) + test_regime_early_classifier: fail standalone, genuinely broken, not mine"), never filed as a queue item until now. `test_no_arm_overtrades`: `risky-1 OVER-trades the backtest: extra=1 > cap 0`. `test_three_arms_entry_faithful`: same bar. Both point at bar 1801 (`2026-06-23 15:35:00-04:00`, side P).

**Root-caused this fire, concretely, via a live debug harness (not guessed):** the shared `decide_payload` verdict at bar 1801 (the SAME deterministic brain `heartbeat_core.py` runs LIVE) reports `triggers_fired: ['level_rejection', 'sequence_rejection', 'trendline_rejection']`, `quality_tier: 'SUPER'`. But `orchestrator.run_backtest`'s OWN independently-implemented trade construction -- called TWICE, once with risky-1's params and once with risky-3's, both fresh `run_backtest()` calls over the identical window -- records `triggers_fired: ['level_rejection', 'trendline_rejection']` for its Trade object at the SAME bar for BOTH arms: `sequence_rejection` is silently absent from run_backtest's own recorded trigger list, even though `orchestrator.py`'s own inline doc (L879/L1181, `has_sequence = seq_trig in winning_triggers`) says a fired `sequence_rejection` DOES count toward ELITE (rank 3) / SUPER (rank 4, >=3 triggers) quality -- so if it HAD been present in run_backtest's own trigger list, run_backtest's own scoring would agree with decide_payload's SUPER call. **`decide_payload` and `orchestrator.run_backtest` are two independently-implemented copies of `detect_sequence_rejection` / level-state (`bounce_history`) tracking that have drifted apart for this specific bar** -- this is a producer(live)-vs-backtest(GT) parity gap in a STATEFUL detector (C12 lesson class: `level_state.bounce_history` needs >=3 touches to fire; state accumulation order/reset semantics likely differ between the two engines), not a dead knob and not a simple off-by-one.

**Why this needs top-tier judgment, not a mechanical fix:** `decide_payload` is what LIVE MONEY actually runs; `orchestrator.run_backtest` is only ever used as an offline approximation/GT for this fidelity harness. That means the MORE LIKELY reading is the GT is what's wrong (run_backtest's own `bounce_history` under-counted a real touch, so the harness's "risky-1 over-trades" alarm is a FALSE POSITIVE born from a backtest-only bug) -- but proving that (vs. the alternative, that `decide_payload` itself is over-firing `sequence_rejection` live and risky-1 genuinely IS taking a lower-quality entry than it should) requires diffing the two engines' `bounce_history` state for the SAME price level leading up to bar 1801, which is a real multi-file state-tracking investigation, not a one-line fix -- and it sits directly on risky-1's live entry-quality gate (`require_confluence_or_sequence`), so a wrong guess either ships a masked live-quality bug or breaks a currently-correct live signal. Exactly the "is this edge/entry legitimate" class OP-0 reserves for escalation, not sonnet-effort guessing.

**Reproduction (verified, cheap, $0):** `pytest backtest/tests/test_replay_fleet_arms.py -q` -> 2 failed, 5 passed. Debug repro script (not committed, ad hoc): replay `PARAMS_BOLD` verdicts via `rfa._replay_verdicts`, read `verdict_by_bar[1801]` (has `sequence_rejection`), then independently call `orchestrator.run_backtest` with risky-1's AND risky-3's own kwargs and inspect `[t for t in res.trades if bar==1801][0].triggers_fired` (missing `sequence_rejection`, both arms). Also note `test_regime_early_classifier` fails standalone too (`KeyError '2026-08-21'` per J's commit message) -- separate, unexplored, likely a lookup table missing today's session; not investigated this fire (would be a second parallel escalation, kept bounded).

**Next step for whoever picks this up:** instrument BOTH engines' `level_state` for the specific price level active going into bar 1801 (likely 735.xx per the verdict's `rejection_level: 735.0`) across the preceding ~30-60 bars, diff `bounce_history` entry-by-entry, and determine which engine's accumulation is the bug before touching either. Do NOT raise `KNOWN_MAX_EXTRA['risky-1']` to paper over this -- that is exactly the "guards that go RED and get waved away" anti-pattern J's own `119bc54e` commit was about (dataset_integrity docstring: "three downstream tests went RED and were NEARLY DISMISSED AS STALE PINS"). :: depends:none :: status:pending

- [x] FUTURES-MIRROR-CROSS-LANE-CLAIM (LOW, filed 2026-08-20 conductor fire) :: Follow-up to arming the MES mirror lane (`Gamma_FuturesMirror --armed`, real bracket orders on Tastytrade sandbox 5WW73759, same account+instrument as `Gamma_FuturesBrokerLane`). Both lanes gate on `broker.is_flat("MES")` which is account-truth so they naturally can't stack on a resolved position, but a same-5-minute-window TOCTOU race (both read is_flat()=True before either places an order) is DISCLOSED not solved -- bounded by paper money + per-trade dollar caps ($100 broker lane / $150 mirror lane) + the account floor reading live combined equity. If this ever needs tightening: reuse the 2026-08-19 SPY-engine atomic-entry-claim pattern (`msvcrt.locking` OS-level exclusive lock, `setup/scripts/heartbeat_core.py::_acquire_claim`) as a shared cross-lane claim file both futures lanes check before placing. Lesson: `strategy/candidates/_lesson-inbox/shared-broker-account-cross-lane-position-attribution-2026-08-20.md`. :: depends:none :: status:pending
  **DEFERRED 03:43 ET 2026-09-03:** still an accurate disclosed risk (bounded by paper money, per-trade caps and broker `is_flat()`); the real fix is porting the SPY `_acquire_claim` file-lock into a futures-only module wired into both armed entry paths -- folded into FUTURES-LANE-WIRING-2 (after-hours, with tests). :: status:pending
  **CLOSED 04:06 ET 2026-09-03:** shipped as FUTURES-LANE-WIRING-2 (b) -- both armed entry paths now take the symbol claim; 28 new tests (contention, stale recovery, release, idempotency). :: status:done

- [x] BOLD-FULLHIST-ANCHOR-DENOMINATOR-CHECK (LOW, follow-up from FLEET-ANCHOR-EXIT-WALK-FIDELITY-DRIFT, filed 2026-08-07 conductor AFTERHOURS) :: `bold_fullhist_replay.py::run_anchor_validation` (core Bold's own anchor validator, a DIFFERENT function/module than the one just fixed) has the textually IDENTICAL `n_pass / len(ANCHOR_FILLS)` denominator pattern -- dormant today only because `ANCHOR_FILLS` is a small, hand-picked, already-OPRA-covered list (`all_pass` currently true per the file's own docstring). Not fixed this fire (different module, bounded-task discipline) -- worth a quick check next time `ANCHOR_FILLS` grows or its pass rate ever drops: verify whether any new anchor entries hit `NO_OPRA_CACHE`/`NO_SPY_DAY` before assuming a fidelity regression, same mistake this fire's parent item made. :: depends:none :: status:pending
  **CLOSED 04:08 ET 2026-09-03 (Sonnet, Fable-verified):** `bold_fullhist_replay.run_anchor_validation` now returns n_anchors / n_evaluable / n_skipped_by_reason / n_pass / pass_rate (over evaluable) / all_pass, mirroring `fleet_arm_replay`'s fix; log line + report show raw and evaluable counts. Two mocked tests, RED-proofed (KeyError before the fix); no replay run. :: status:done
- [x] GATE-EXPIRY-SOLE-BLOCKER-MINER (HIGH) :: Extend backtest/autoresearch/gate_expiry_check.py with the filter-checklist sole-blocker miner now proven in backtest/tools/postfix_gate_costing.py (HOLD rows, bear_blockers/bull_blockers == [N], per door) so filters 1-11 get the same nightly refusal-costing clock the SKIP gates have -- flagship watch: bear sole-[8] (VIX floor 17.3 on a breakdown day with VIX under the floor; post-fix count is 0, see analysis/recommendations/vix-bear-floor-postfix-quantification-2026-08-04.json) and bull sole-[10] (buyer pressure, prereg bull-f10-buyer-pressure-prereg-2026-08-04.json awaits its full-population runner) :: depends:none :: status:pending
  **DONE 2026-09-03 01:48 ET (Sonnet, Fable-specced):** `gate_expiry_check.py` now mines sole-blocker HOLD rows per door via `postfix_gate_costing.sole_blocker_rows()` (lazy import), 20-session rolling window, flagship watches `filter-8-bear-sole` / `filter-10-bull-sole` transition-flagged; output additive in `automation/state/gate-registry-status.json` (`sole_blocker_miner`). costing = NOT_REPLAYED (same-day P1 outcome proxy). **LIVE FINDING:** bear sole-[8] is NOT 0 anymore -- 106 clustered events over 14 of the last 20 sessions (44 read cost_money by proxy) -> RED; bull sole-[10] 78 events (28 cost_money) -> RED; bull sole-[5] 80, sole-[11] 66. 20 tests, 66 passed with the neighbours, 3 mutations RED-proofed. Follow-up filed: BEAR-F8-VIX-FLOOR-COSTING-REPLAY. :: status:done
- [ ] BULL-F10-PREREG-RUNNER (MED) :: Execute the frozen bull-f10-buyer-pressure-prereg-2026-08-04.json cells (f10_vol_mult 0.7/0.5/0.35/0.0) on the full 391-day real-OPRA population via the standing battery; verdict per the prereg's frozen gates; decision floor n>=20 added-cohort :: depends:none :: status:pending
- [ ] BREAKDOWN-VOCABULARY-GAP (MED, frozen prereg ONLY -- do NOT build the naive version) :: **THE GAP:** the live setup vocabulary is exactly four names -- `BEARISH_REJECTION_RIDE_THE_RIBBON`, `BULLISH_RECLAIM_RIDE_THE_RIBBON`, `VWAP_CONTINUATION`, `VWAP_RECLAIM_FAILED_BREAK`. Every one of them is a REJECTION or a RECLAIM: they all require price to APPROACH a level and TURN AT IT. **There is no setup that can trade a level that BREAKS and KEEPS GOING.** A clean break-and-run is currently untradeable by construction, not by policy -- no gate rejects it, no vocabulary exists to name it. Note the 08-06 put worked because 770.24 broke and ran, but the engine entered it as a *rejection* of the reclaim attempt, i.e. we caught a breakdown through the only door we own, not through a door built for it. **WHY THE NAIVE VERSION IS FORBIDDEN (read before designing):** C20 -- *gate direction must match setup structure; proximity gates ANTI-CORRELATE with breakout setups* (L102, L219). Every level-tied trigger we own is built on proximity-to-level. A breakout setup wants DISTANCE from the level and ACCELERATION away from it, so bolting a breakout trigger onto the existing proximity plumbing inverts the gate and reproduces the exact failure C20 already documents twice. Also note C27 (a detector firing >80% of days measures noise -- levels 'break' constantly; the discriminator is what happens AFTER) and C28 (ribbon is a LAGGING confirmation -- a break-and-run setup AND-gated to a ribbon flip will fire after the move is over, the same way the filter-5 bull entry did on 08-06 at 14:21 for -$36). **DELIVERABLE IS A FROZEN PRE-REGISTRATION, NOT CODE.** It must state, before any runner: (a) the structural definition of break-and-run that DISCRIMINATES it from the failed-break we already trade (candidate axis: post-break follow-through within N bars + no return inside the zone, per J's supply/demand + structure-shift philosophy); (b) which gates must be INVERTED rather than reused, named individually with their C20 rationale; (c) the population frequency FIRST (C27 prescreen -- if it fires on >80% of days it is noise, kill before building); (d) real-OPRA expectancy on the 391-day population with OOS + regime stratification, never WR alone; (e) an explicit no-harm gate against the EXISTING four setups (a new door must not cannibalise the rejection book). **Honest prior:** breakout systems are the most over-fit family in retail 0DTE and this one has to clear a book that is currently profitable on rejections. Frequency prescreen first -- it is the cheapest kill. :: depends:none :: status:proposed
> **Archive note (2026-08-09):** 14 fully-resolved sections (old Archived/Completed + 12 stale-but-closed dated sections, 1019 lines) were relocated verbatim to `queue-archive-2026-08.md` this date to keep this file under the Read tool's 256KB limit. Nothing open was moved -- see that file's own header for the verification method.
>
> **Archive note (2026-08-19):** the file had silently regrown to 598,612 bytes (2.3x the Read limit) in the 10 days since the note above. 119 fully-resolved `[x] status:done/closed/resolved/cancelled/decided` items (69 top-level, plus resolved items in later dated sections) relocated verbatim to `queue-archive-2026-08-19.md` -- verified zero `depends:` breakage before removal, `task_scorer.py --all` re-parses correctly post-move (91 items, 51 ready), curated safety gate 59/59 PASS. Now code-guarded: `backtest/tests/test_queue_md_retention_cap.py` RED-fails past 450,000 bytes so this can't regrow silently a third time. Commit `60eb232e`.

> **Archive note (2026-08-29, QUEUE-MD-RETENTION-CAP step 3):** 29 fully-resolved checklist items (explicit `[x]` or CLOSED/DONE status) + 16 duplicate `gamma_manager` ESCALATION auto-harvest lines were relocated verbatim to `queue-archive-2026-08-29.md` this date to keep this file under the Read tool's 256KB limit. Nothing open was moved -- see that file's own header for the verification method. The one concrete finding buried in the removed noise (T-OPEN-TICK-STALE-QUOTE-2026-08-20, tick freshness check) is re-filed just below as its own item so it isn't lost.
>
- [x] TICK-FRESHNESS-VALIDATION-2026-08-20 (MED, re-filed 2026-08-29 from archived ESCALATION noise, concrete finding extracted from 16 duplicate auto-flags) :: `gamma_manager` repeatedly flagged (71x since 2026-08-21, never actioned) that tick validation lacks a timestamp-freshness check, allowing gap-and-go entries on stale quotes -- named incident T-OPEN-TICK-STALE-QUOTE-2026-08-20. Verify whether this is still live (check current tick-ingest code for an existing freshness/staleness guard before assuming the gap is real) and either close as already-covered or add a 2-bar freshness buffer with a guard test. :: depends:none :: status:pending
  **CLOSED (covered + detector) 04:08 ET 2026-09-03 (Sonnet, Fable-verified):** the incident's only numbers live in a manager artifact stamped `QUARANTINED -- FABRICATED` (`analysis/manager/2026-08-23-0233-*.md`); the 71 escalations are one generic line repeated. What exists in code: `heartbeat_core._trigger_bar_stale` writes `bar_freshness{age_min,stale}` on EVERY tick (threshold 20 min) and its docstring deliberately does not gate on it pending OP-11 evidence; a separate price-divergence guard (`SIGHT_STALENESS_MAX_DIVERGENCE_USD` $1 -> `SKIP_STALE_SIGHT`, ~30 tests) DOES gate entries. New read-only `setup/scripts/tick_freshness_audit.py`: 1,174 rows in the full ledger have a same-session bar > 2 bars old -- **all HOLD/SKIP/NOT_FLAT, zero entries**, 3 already caught by the sight guard; a naive age gate would fire on ~20% of idle ticks. Not a live bug. Bundle-spec (frozen file): wire `bar_freshness.stale` into a `SKIP_STALE_BAR_FRESHNESS` veto behind an injected clock -- low urgency, recorded here for the 09-29 bundle menu. :: status:done

- [x] QUIET-MODE-BLACKS-OUT-THE-SUNDAY-FUTURES-OPEN (HIGH, filed 2026-08-29 Fable futures review â€” the 2026-08-26 starvation lesson recurring in a shape its own guard cannot see) :: CME equity-index futures trade **Sunday 18:00 ET â†’ Friday 17:00 ET** (daily 17:00â€“18:00 ET maintenance break). `setup/scripts/quiet_mode.py`'s bands are: 23:00â€“08:00 LOUD any day Â· **weekend = QUIET** Â· weekday 18:00â€“23:00 QUIET Â· weekday 08:00â€“18:00 LOUD. So **every Sunday 18:00â€“23:00 ET â€” the first five hours of the futures trading week â€” every futures task is Disabled**, and weekday evenings 18:00â€“23:00 (also live GLOBEX time for a 24/5 instrument) are blacked out too. `ESSENTIAL` (L72-90) exempts the SPY trading chain by name on exactly the stated rationale "the trading chain, so a market day is never lost to quiet mode" â€” futures has no equivalent exemption because `ESSENTIAL` is 100% SPY-named. **Why the existing guard misses it:** `backtest/tests/test_quiet_mode_starvation.py` fails a task only when its reachable fire-hours are a SUBSET of blackout hours; futures tasks also fire during weekday RTH, so they are partially starved, not fully â€” the guard passes while the lane loses the session open every single week. **RECOMMENDED (my call, needs implementing with blast-radius care):** add the futures TRADING chain (`Gamma_FuturesTrader`, `Gamma_FuturesBrokerLane`, `Gamma_FuturesMirror`) to `ESSENTIAL` on the identical rationale that already exempts the SPY chain. âš ï¸ PRE-CONDITION before doing so â€” verify each of those tasks launches through the hidden-window chain (wscriptâ†’pythonw / `run_cmd_hidden.py`), because quiet mode exists to keep popups and CPU off J's evening and a window-flashing task in `ESSENTIAL` would re-create his #1 complaint; check `window-leak-detector` history for these task names first. Also extend `test_quiet_mode_starvation.py` with a SESSION-AWARE case: for an instrument whose market is open, no trading-chain task may be Disabled â€” that is the assertion that would have caught this. NOT Monday-blocking (Monday 08:00 ET onward is LOUD, so the weekday lane runs), but it costs the Sunday open every week until fixed. :: depends:none :: status:done **CLOSED 2026-09-01 (conductor AFTERHOURS):** verified pre-condition live (all 3 launch via the flash-free wscript->run_exe_hidden.vbs->pythonw chain, grepped their installers) then added `Gamma_FuturesTrader`/`Gamma_FuturesBrokerLane`/`Gamma_FuturesMirror` to `quiet_mode.ESSENTIAL`; added `test_essential_set_covers_the_futures_trading_chain` (RED-proofed: failed naming the exact 3 missing names with the fix stashed, green restored). No live behavioral change today (all 3 already trigger only inside the LOUD weekday RTH band) -- closes the gap for a future Sunday-open producer. Curated safety gate 59/59. Commit `a6ccc6c5`. Revert: `git revert a6ccc6c5`.
- [x] FUTURES-PREMARKET-PRODUCER-MISSING (HIGH, filed 2026-08-29 Fable futures parity audit) :: `Gamma_FuturesPremarket` has **NEVER FIRED** â€” live Task Scheduler shows `LastRunTime=11/30/1999`, `LastResult=267011` (`SCHED_S_TASK_HAS_NOT_RUN`), Disabled since 2026-07-08, and it targets June-era corpse state (`automation/state/futures/position.json`/`account.json`/`risk.json`, all last written 2026-06-17..07-14). Its persona `automation/prompts/futures-premarket.md` reads those same dead files. **Unlike `Gamma_FuturesEod` â€” which has a working successor in `Gamma_FuturesEod2` â€” Premarket has NO successor**, so the futures lane has no equivalent of SPY's 08:30 level/bias/hypothesis prep at all. Build a deterministic (NOT LLM, $0) `backtest/futures/futures_premarket.py` writing an MES-equivalent of key-levels/today-bias before the RTH open, register it, and formally retire the dead task + persona rather than leaving a never-fired task on the registry implying coverage that does not exist. NOTE: `Gamma_FuturesPremarket` and `Gamma_FuturesEod` are NOT in `quiet-mode-restore.json` (they were already Disabled when quiet mode captured state) so they will never self-restore â€” retiring or replacing them is a deliberate act. :: depends:none :: status:pending
  **DONE 2026-09-03 01:08 ET (Sonnet, Fable-specced):** `backtest/futures/futures_premarket.py` (deterministic, $0, no LLM) registered as `Gamma_FuturesPremarket2` (08:35 ET weekdays; hand-fired exit=0), the never-fired `Gamma_FuturesPremarket` unregistered (was LastResult 267011 / LastRun 1999), persona retired to `automation/prompts/_retired/`. Writes `automation/state/futures/{key-levels,today-bias}.json` for MES+MNQ with DATA_MISSING-never-fabricate semantics (live run: MES prior_close 7678.5, bias neutral conf 0.174). 13 tests, 3 mutations RED-proofed; registry count unchanged (1-for-1 swap), gate 5/5. **No consumer wired** -- `futures_trader_core`/`futures_heartbeat_core` derive levels internally; wiring is a lane-behaviour change, filed as FUTURES-PREMARKET-LEVELS-CONSUMER. :: status:done
- [x] FUTURES-MISTAKES-LEDGER-IS-DEAD-CODE (MED, filed 2026-08-29 Fable futures parity audit, C14 dead-knob class) :: `backtest/futures/futures_journal.py:178` defines `record_mistake()` and **`grep -rn record_mistake --include=*.py .` returns ZERO call sites repo-wide**; `journal/futures/mistakes.md` does not exist on disk. `futures_eod.py::rule_audit()` detects rule breaks but never persists them there. So the futures analogue of Rule 8's mistakes ledger is documented, implemented, and never invoked â€” the exact shape of a safety net that exists only on paper. Wire `rule_audit()`'s findings into `record_mistake()`, create the ledger, add a guard test asserting a detected break actually lands a row. :: depends:none :: status:pending
  **FIXED 2026-09-03 01:22 ET (Sonnet, Fable-specced):** `futures_eod.py::build()` calls new `persist_mistakes()` right after `rule_audit()`, wiring findings into `journal/futures/mistakes.md` via `futures_journal.record_mistake()` (call site `futures_eod.py:346`). Idempotent per (date, rule, lane) via an inline dedupe marker, fail-open. Guard `test_futures_mistakes_ledger_2026_09_03.py` 10/10 incl. an AST call-site check; 4 mutations RED-proofed; 97 passed across the futures EOD/journal suites. Real run 01:21 ET: 0 breaks (session not open) -> ledger correctly not created. UNVERIFIED until a real rule-break day: one-row-per-rule on live data. :: status:done
- [x] FUTURES-ABSENT-FROM-GO-LIVE-GATE (MED, filed 2026-08-29 Fable futures parity audit) :: `setup/scripts/go_live_gate.py` contains exactly ONE futures mention â€” a disclaimer that the Kalshi/SSR shadows "neither substitutes for" the SPY criteria â€” and evaluates no futures criteria at all. `live_readiness.py` tracks only the dormant/pending arms (`mes-linear-sim`, `mes-mnq-div-futures`), not the CURRENT `Gamma_FuturesTrader`/`Gamma_FuturesBrokerLane` lanes (which post-date that code). Consequence: there is no promotion gate a futures lane could ever pass, so "is futures ready for more capital" has no instrument and would be answered by vibes. Extend the gate with futures-appropriate criteria (dollar/point-denominated, margin-aware per `markdown/futures/MARGIN-LEVERAGE-RISK.md`, reconciliation vs the sandbox account) reusing `statistical_criterion()` where the shape fits. Do NOT reuse the SPY PF-CI thresholds unexamined â€” futures P&L is uncapped-loss and margin-constrained, a different distribution. :: depends:none :: status:pending
  **DONE 2026-09-03 02:30 ET (Sonnet, Fable-specced):** `setup/scripts/futures_go_live_gate.py` -- a SEPARATE advisory ladder (F1 statistical: day-level bootstrap PF CI-lower on REAL broker fills, >=20 scored sessions; F2 margin: worst-case per-trade loss vs the lane's daily limit + open margin at the high end of MARGIN-LEVERAGE-RISK vs equity; F3 reconciliation: >=80% round-trip agreement fillsim vs sandbox; F4 operational: futures_health.py folded verbatim, stale -> INSUFFICIENT), all thresholds PROVISIONAL with reasons in code, wired additively into `go_live_gate.py` as a sibling `report['futures']` key + printed section; SPY `overall_verdict` proven byte-identical (RED before/after), `render_markdown` untouched, fail-open wrapper RED-proofed. Live: **lane RED -- F1/F3 INSUFFICIENT with 0 real closed round trips, F4 RED (connect-failure 43%)**. 27 tests. Filed FUTURES-BROKER-LANE-NEVER-LOGS-EXITS. :: status:done
- [x] FUTURES-POST-TRADE-AUTOPSY-MISSING (LOW-MED, filed 2026-08-29 Fable futures parity audit) :: SPY has `winner_autopsy.py` + `winner_signature.py` + `trade_autopsy.py` all scheduled and feeding `analysis/winner-autopsies/`; futures has none (`find` for `*autopsy*` returns only the three SPY scripts, and the `analyst` skill has zero futures mentions). `futures_eod.py::rule_audit()` is a compliance check, not pattern-mining â€” nothing ever asks "what does futures money look like". Build `backtest/futures/futures_autopsy.py` modeled on `trade_autopsy.py`, scheduled after `Gamma_FuturesEod2`. Lower priority than the SEV-1 execution fixes: pattern-mining a lane that has taken 9 real fills total is premature â€” do this AFTER the lane is reliably filling. :: depends:none :: status:pending
  **CLOSED 03:43 ET 2026-09-03 (Sonnet, Fable-verified):** `backtest/futures/futures_trade_autopsy.py` reads `journal/futures/trades.csv`, MAE/MFE best-effort from the lane's `MES_5m_live.csv`, writes `analysis/futures/autopsy-latest.{md,json}`, never raises. First run on the 3 real sandbox round trips: 08-31 OPEN_REJECTION short TP1_FULL +$16.25 (1.7 min); 08-31 LEVEL_REJECT_LIVE short BROKER_CLOSE -$67.50 (MAE 22.50 pts, 60 min); 09-02 ERL_IRL_SWEEP_FVG short FULL_STOP -$42.50 (13 min); total -$93.75, matches the reconciler. Scheduled task not yet registered (after Gamma_FuturesEod2) -- folded into FUTURES-LANE-WIRING-2 below. :: status:done
- [x] FUTURES-WEEKLY-REVIEW-MISSING (LOW, filed 2026-08-29 Fable futures parity audit) :: `grep -rl futures .claude/skills/treasurer/` â†’ zero matches; `Gamma_ConductorWeekend`'s own doc punts futures findings to `queue.md` rather than performing a weekly futures risk/sizing review. SPY gets a treasurer weekly + WEEK ORDER; futures gets neither. Either extend `treasurer`'s scope to `journal/futures/trades.csv` + `eod-summary.json` history, or add a dedicated weekly futures pass. Fold into WEEK-ORDER-CADENCE-REVIVAL rather than creating a parallel weekly surface. :: depends:none :: status:pending
  **FOLDED 04:53 ET 2026-09-03 (Fable):** per the item's own instruction, no parallel weekly surface -- the Thursday-evening WEEK ORDER synthesis (WEEK-ORDER-CADENCE-REVIVAL, due tonight 2026-09-03 evening per the work order) gains a fixed futures section: `journal/futures/trades.csv` week P&L, `analysis/futures/autopsy-latest.md` (new tonight), `ssr-fundability.json` gauge, `futures_health` RED count, open anomalies. Recorded on the WEEK-ORDER item; nothing else to build. :: status:folded
- [x] FUTURES-ARMED-HORIZON-VIOLATES-MARGIN-DOCTRINE (**CRITICAL**, filed 2026-08-29 Fable futures review â€” a real auto-liquidation exposure, must be closed BEFORE the armed lane places another order) :: `setup/scripts/futures_mirror_shadow.py` arms REAL sandbox orders with `ENTRY_QTY = 2` (L271) and `rails = FuturesRiskRails(max_contracts=ENTRY_QTY, per_trade_risk_cap=BROKER_PER_TRADE_RISK_CAP)` (L653-654, overriding the rails' own `DEFAULT_MAX_CONTRACTS = 1` / `DEFAULT_PER_TRADE_RISK_CAP = 100.0`), on a **2-SESSION (overnight) horizon** (module docstring L35-36: "flat by 15:55 ET on the NEXT trading day"). That directly violates this project's own ratified futures doctrine, `markdown/futures/MARGIN-LEVERAGE-RISK.md`: L28 "For a $2K sandbox account... holding overnight could exceed account equity. **Stay intraday, stay in micros**"; L54 "**Intraday only:** avoids overnight/initial margin entirely while learning"; L18 "Hold past the cutoff and the full overnight/initial margin snaps back â€” if the account can't cover it, the broker may **auto-liquidate** the position and charge fees." `futures_risk_rails.py` already encodes the correct behaviour (`MINUTES_BEFORE_MAINTENANCE_BLOCK=30`, `MINUTES_BEFORE_MAINTENANCE_FLATTEN=10`) â€” the mirror's armed path simply doesn't honour the horizon side of it. **ROOT OF THE MISMATCH:** the mirror was designed as a pure SHADOW, where a 2-session horizon costs nothing because no capital is at risk; it was then ARMED for real orders 2026-08-20 without reconciling that horizon against the margin doctrine. This never bit us only because every armed attempt since has died on transport (see FUTURES-PROBE-TAXONOMY-AND-SILENT-SKIPS) â€” i.e. a bug was the only thing preventing the exposure. **DECIDED (Gamma-decides, paper, reversible), to implement:** split the two concerns â€” (a) the ARMED broker path goes **intraday-only, qty=1, flat before the maintenance cutoff**, honouring `futures_risk_rails` defaults rather than overriding them, and stamps each row with an explicit `armed_spec` field naming the deviation; (b) the **would-be shadow ledger keeps its 2-session spec UNCHANGED** so the 94-round-trip evidence series is not corrupted mid-stream. âš ï¸ Because (a) and (b) now measure different things, they must NEVER be compared as the same strategy â€” label both ledgers accordingly. Guard: a test asserting the armed path cannot construct rails looser than the module defaults, and cannot hold past the maintenance cutoff. :: depends:none :: status:pending
  **CLOSED 03:43 ET 2026-09-03 (verified, shipped 08-29):** `futures_mirror_shadow.py` armed leg is intraday-only -- `_broker_maintenance_flatten()` consults `FuturesRiskRails().must_flatten(now_et)` before any entry, cancels+closes inside `MINUTES_BEFORE_MAINTENANCE_FLATTEN=10`, refuses entries inside `MINUTES_BEFORE_MAINTENANCE_BLOCK=30`; guard `test_futures_mirror_armed_intraday_2026_08_29.py` 17 passed; futures suite 450 passed. ENTRY_QTY stays 2 (documented deviation: the defect was the horizon, not the size). Tonight's `3037fbe4` closed the separate FLATTEN-cascade class; no overnight exposure path remains. :: status:done
- [ ] SAFE-2-EXIT-SHAPE-AB-PREREG-V2 (MED, trading-path, prereg-first, DEFERRED â€” do NOT pick up until the September scoring window closes ~2026-09-29, filed 2026-08-29 replacing the killed v1 immediately above) :: The v1 item died because two analyses disagreed on the SIGN of the `tp1_premium_pct` effect and NEITHER was single-variable (v1's proxy said +$1,050; the 37-signal natural A/B said -3.74 pct-of-premium, -18.24 pp on winners). The underlying QUESTION is still open and still worth answering: **does an earlier TP1 trigger help or hurt, holding everything else fixed?** SHIP SHAPE (all four required): (1) **single-variable** â€” vary `tp1_premium_pct` ONLY, with `profit_lock_mode` and `stop_mode` held identical across both sides, because safe-3/risky-1 differ in profit_lock_mode and that confound is what makes both existing analyses un-attributable (lesson C29); (2) **right-tail preservation check as a first-class kill criterion** â€” report the conditional effect on trades returning >+30% separately from the pooled mean, since the pooled median is 0.00 and the entire effect lives in the tail; a variant that improves the mean by clipping the tail FAILS; (3) **per-wave, not per-fill**, with ex-best-day reported on every claim (design rule 5); (4) **run OUTSIDE a scoring window** â€” never push a trading-path change into the 20 days the go-live gate is measuring. Note the natural experiment regenerates itself for free: risky-1 and safe-3 keep taking identical contracts on identical days (37 so far), so this can be answered by ACCUMULATING that paired sample rather than by changing any config â€” prefer that route, it costs nothing and risks nothing. Re-check n on the shared-signal set before building anything. :: depends:none :: status:blocked
- [x] GO-LIVE-GATE-TRAILING-WINDOW-VIEW (MED, filed 2026-08-29 Fable full review) :: go_live_gate.py statistical criterion scores each arm's full trade history (29-42 day windows reaching back into the July regime) -- J's recency-over-aggregate doctrine (2026-07-31, every armed gate needs a revalidation clock) applied to the gate itself: add a trailing-20-trading-day scored view per arm alongside aggregate (same three-view bootstrap, clearly labeled, NEVER replacing the aggregate view -- disclosure, not bar-softening; the pass criterion stays aggregate until J ratifies otherwise). Purpose: the September clean window (08-31..~09-29) must be readable on its own merits each Friday without July ghosts. Source: FABLE-FULL-REVIEW-2026-08-29.md section 5. :: depends:none :: status:pending
  **CLOSED 03:41 ET 2026-09-03 (Sonnet, Fable-verified):** `go_live_gate.trailing_20d_view()` writes `disclosures.trailing_20d` per arm (as-traded / ex-best-day / cost-adjusted PF CI-lower 2.5%, n_days, window, 'DISCLOSURE ONLY -- not a bar'); the verdict path never reads it (mutation-proofed in `test_go_live_gate_trailing_20d_2026_09_03.py`, 4 passed). Builder's before/after `--no-refresh` diff: criteria 1-5 + verdict byte-identical. Tonight's trailing-20d (all FAIL, CI-lower 0.35-0.43): safe-3 07-15..09-02, safe-2 08-04..09-02, risky-1 07-15..09-02, bold-2 07-02..09-02. Note for Friday: the fresh run also absorbed the 09-02 session -- book-wide as-traded PF 1.205 -> 1.124, ex-best-day total -$827 -> -$1,526; safe-3 as-traded 1.385 -> 1.262 (n_days 27). :: status:done
- [ ] FUTURES-PROBE-TAXONOMY-AND-SILENT-SKIPS (MED, filed 2026-08-29 Fable full review, C7 class) :: Two defects + one decisive test in the tastytrade sandbox lane. (1) futures_broker_probe.py lines ~110-126: the fallback else-branch maps ANY non-session exception to H1_PERMISSIONS -- broker-probe.jsonl rows 20-21 (08-27/08-28) are literal "ReadTimeout:" mislabeled as permissions rejections. Fix taxonomy: timeouts/network -> their own verdict (H3_TRANSPORT or similar); RED-proof. (2) mirror-broker-orders.jsonl: 8 real-order attempts since 08-20 armed, 0 confirmed placements, 7 rows with NO reason field -- every non-placement must log why (C7). (3) Then the decisive evidence: ONE real small marketable MES order on a confirmed-open GLOBEX session (a real fill already happened once, 2026-08-09 per SCHEDULED-TASKS.md:154, contradicting is_futures_approved:false and the uncited "cert env is equities-only" claim in FUTURES-BROKER-RESEARCH-2026-08-09.md's 08-21 update) -- settle H1-vs-H2 on fresh evidence instead of a 4th week of dry-run probes. If the real order is REJECTED with a broker-side permissions error: escalate to J (tastytrade dashboard check, or the researched Tradovate-demo fallback -- account creation is J-only). Source: FABLE-FULL-REVIEW-2026-08-29.md section 4. :: depends:none :: status:pending
  **PARTIAL 03:43 ET 2026-09-03:** (1) taxonomy and (2) no-silent-skips were already shipped 08-29 (`futures_broker_probe._classify_probe_verdict`, `futures_mirror_shadow._broker_execute_entry.failure_detail`; guard `test_futures_broker_transport_2026_08_29.py` 12 passed). (3) the decisive real-order probe needs an actual marketable sandbox order -- not allowed in tonight's read-only broker session; run it in the same supervised slot as FUTURES-NATIVE-OCO-DRY-RUN. :: status:partial
- [ ] WEEK-ORDER-CADENCE-REVIVAL (MED, filed 2026-08-29 Fable full review) :: The Thursday-evening WEEK ORDER synthesis lapsed -- last one is WEEK-ORDER-2026-08-10.md (written 08-06); three weeks of armed-state changes (risky-3 retirement, weekly-1 creation, 08-24 bollinger/vwap-reclaim disarm, quiet-mode bands, gate-recency closures) live only in STATUS/queue scroll. Produce WEEK-ORDER-2026-08-31.md this weekend (same 7-lane sweep format, "FOR J -- 12 LINES MAX" header) and restore the weekly cadence; MAP.md's routing table still points at the 08-10 doc as "what is armed right now". :: depends:none :: status:pending
  **NOTE 04:53 ET 2026-09-03:** tonight's synthesis (Thursday evening, after 16:00 ET) must include a futures section (folded from FUTURES-WEEKLY-REVIEW-MISSING): week P&L from `journal/futures/trades.csv`, `analysis/futures/autopsy-latest.md`, `ssr-fundability.json` gauge, `futures_health` RED count, open anomalies.
- [x] TRENDLINE-SHADOW-VERDICT-RECOMPUTE (LOW, filed 2026-08-29 Fable full review) :: analysis/trendlines/shadow-ledger.jsonl has grown to 4,786 rows through 08-28 but the last computed statistical verdict is dated 2026-08-20 (65 sessions, +0.041 pts/trade, session-clustered CI [-0.039,+0.124] straddling zero, top-3 sessions >100% of profit). Recompute the same verdict on the current ledger (same method, no new knobs) and re-stamp SCHEDULED-TASKS.md:190 + SHADOW.md source so the lane's evidence isn't quoted 9+ days stale. Also: no pre-registered numeric promotion bar was found for this lane -- freeze one (CI-clears-zero + concentration-resolved + explicit n) so promotion can't be argued qualitatively later. :: depends:none :: status:pending
  **CLOSED 03:47 ET 2026-09-03 (Sonnet, Fable-verified):** the 08-20 verdict had no script (one-off at ship time, `ed8e78bd`); `setup/scripts/trendline_shadow_verdict.py` now recomputes it (session-resample bootstrap, seed 1337, n=2000, 95% CI). Old: 65 sessions, n=1,332, +0.041 pts/trade, CI [-0.039, +0.124]. **New through 09-02: 73 sessions, n=1,451, +0.0386 pts/trade, CI [-0.0301, +0.1177], top-3 sessions = 105% of profit** -- still straddles zero, still concentrated. Promotion bar FROZEN in `analysis/trendlines/shadow-verdict.json` (append-only history): CI-lower > 0, top-3 < 50% of profit, n_sessions >= 60, no new knobs. SHADOW.md had NO row for this lane at all -- generator gap fixed in `obsidian_vault_sync.build_preregs_board` (reads the verdict file). Registry row text refreshed. 9 + 16 + 17 passed. :: status:done

## Active backlog
> 2026-09-03 18:30 ET: 15 `[x]` done items (25,523 bytes) moved verbatim to `queue-archive-2026-09-03.md` (cap 450,000 -- see test_queue_md_retention_cap.py).
> 2026-09-02 23:58 ET tranche 2: 8 more `[x]` done items (19,483 bytes) moved verbatim to `queue-archive-2026-09-02.md` (cap 450,000 -- see test_queue_md_retention_cap.py).
- [ ] GOAL-COCKPIT-REDESIGN-2026-09-03 (HIGH, goal) :: Command-center overhaul: real design assets, Army+Autonomy merged, expandable tiles for every producer, judged >=7/10 (J 2026-09-03 18:50 ET) -- file: automation/state/goals/GOAL-COCKPIT-REDESIGN-2026-09-03.md :: depends:none :: status:in_progress
- [ ] GOAL-GAMMA-AUTONOMY-2026-09-03 (HIGH, goal) :: Gamma opens and drives its own goals; learning ledger; Autonomy tab on the home page (J 2026-09-03 17:41 ET) -- file: automation/state/goals/GOAL-GAMMA-AUTONOMY-2026-09-03.md :: depends:none :: status:done
### FABLE-FULL-AUDIT-2026-09-01 follow-ups (filed 2026-09-01 ~21:00 ET; source: analysis/deep-research/FABLE-FULL-AUDIT-2026-09-01.md; provenance analysis/deep-research/2026-09-01-audit/findings.json)
> Execution order + phases + drills for every session until 2026-10-30: `markdown/planning/OPUS-WORK-ORDER-2026-09.md` (tick boxes there as these land).
- [x] NULL-LEGS-WALK-STRUCTURE-ONLY (MEDIUM, disclosure now / prereg revision later, filed 2026-09-01 Opus) :: `walk_one`'s hardcoded `structure_stop_enabled=True` also reaches both null legs (`run_null_a` ~line 616, `run_null_c` ~line 728), so the nulls are a structure-only variant of an engine whose real P1 population resolved **structure 107/156 = 68.6% / premium 42/156 = 26.9% / none 7/156 = 4.5%**. N_c is the sharper case: it replays the engine's OWN entries, which each carry a recorded stop_mode it ignores. DELIBERATELY NOT CHANGED IN-WINDOW -- the prereg is frozen and specifies the null design, and altering a null leg after seeing the study's results is the exact post-hoc pattern the 2026-09-01 addendum incident already had to reverse. Shipped as a `known_limitations` disclosure instead; reconciling it needs a prereg revision, not an edit. :: depends:none :: status:pending
  **PREREG V2 FILED 04:26 ET 2026-09-03 (Sonnet draft, Fable read):** `analysis/recommendations/prereg-whole-engine-null-v2-stop-mode-faithful-2026-09-03.md` -- N_c threads each entry's recorded `stop_mode` into `walk_one`; N_a draws stop_mode by seeded stratified sampling from the empirical mix (0.686 / 0.269 / 0.045, taken from this item's text, NOT recomputed -- flagged); N_b untouched; walker, criterion, populations, bootstrap, thresholds, vocabulary byte-identical to v1. Effective 2026-10-02 (first Friday after the 09-29 checkpoint), v1 published beside it for two Fridays. Pre-committed prediction: a favourable structure-only bias would show as N_c moving away from <= 0; refuted if N_c stays <= 0 or moves more negative. `build_step: {file: setup/scripts/whole_engine_null.py, symbol: run_null_c, must_contain: 'stop_mode=row.get("stop_mode")'}`. v1 stays the published reading with its known_limitations disclosure until then. :: status:prereg-filed
- [~] EXECUTED-STOP-FIELD-SPEC (HIGH, kill-type-SAFE logging, SHIP IN THE 09-29 BUNDLE, spec'd 2026-09-02 Opus) :: **BUILT 2026-09-02 on branch `safety-bundle-2026-09-29`, commits `93a3ccc3` + `d7c0b3db` -- BOTH HALVES DONE, awaiting the 09-29 merge.** Writer landed in `exit_actuator.manage_tick` (the real caller -- NOT heartbeat_core/fleet_executor as this spec assumed; it already logged the pre-tick floor as `stop_premium`, unnamed). `executed_stop_price` is opportunistic: Alpaca's order-CREATE response carries `filled_avg_price: null`, so it records None rather than fabricating, and the fill joins later by order_id. 25 tests, 3 mutations RED-proofed. The five armed-stop fields + `stop_exit_slack_dollars()`/`executed_stop_pct()` helpers are in; `heartbeat_core`/`fleet_executor` must still persist them alongside `executed_stop_price`. Attached by a WRAPPER so the decision body is byte-identical (115 insertions, 1 deletion = the `def` rename) rather than editing 14 return points. The snapshot reads the PRE-tick floor -- on a trail exit the chandelier ratchets and sells in the same tick (1.70 -> 2.275) and the post-tick value never guarded the position; that mutation ESCAPED the first guard and the guard was strengthened. 21 tests, 2 mutations RED-proofed. NOT merged: exit_manager.py is frozen to 2026-10-30. ORIGINAL SPEC BELOW :: Closes work-order §2a `planned_stop != executed_stop`. **The 79% 'mismatch' is NOT a bug** -- it decomposes into three benign classes (measured on 348 engine rows with both fields): (1) **structure-mode rows, 53%** -- `planned_stop` records the -50% CATASTROPHE CAP premium (ratio to entry_px median **0.503**, 80% within +/-0.03 of 0.50, n=186) while the operative invalidation is a SPY chart level living only in `trigger_level` / the `stop_display` string (`STRUCTURE@754.00 (cat -50%)`); 77% of structure stop-exits filled ABOVE the cap, median **+$0.275/contract** -- chart-stop-primary working, not a defect. (2) **trailed exits, 53/53 = 100%** -- the chandelier ratchets the floor up after entry and NOTHING writes it back, so the entry-time field is stale by design; median +$1.207 above it at a median **+91.4% realized return** (they exited in PROFIT, which an entry-time stop price cannot describe). (3) every exit is an unconditional MARKET order, so even a premium stop fills at touch +/- spread. **SPEC -- add at ARM time:** `armed_stop_kind` (`structure_level`|`premium_stop`|`catastrophe_cap`), `armed_stop_level` (SPY price; alias of trigger_level), `armed_stop_premium` (the floor in force at entry). **Add at EXIT time -- this is the real gap, nothing records exit-time state today:** `executed_stop_price` (the fill), `executed_stop_pct` (= fill/entry_px - 1), **`armed_stop_at_exit_premium`** (the floor in force AT THE MOMENT OF EXIT, post-ratchet -- **the load-bearing field; without it no trailed exit can ever be reconciled**), `armed_stop_at_exit_level`, and `stop_exit_slack_dollars` (= executed_stop_price - armed_stop_at_exit_premium) -- **that last one is the true execution-quality measure and is what the gate's 2c slippage assumption should be recalibrated against**, pairing with the quote tape. **Guards to ship with it (same invariant class as the 2026-09-01 trigger_level guard):** any stop-class exit must have non-null `armed_stop_at_exit_premium`; any structure-mode row must have `armed_stop_kind=='structure_level'` and non-null `armed_stop_level`. **Freeze-compatible as a 09-29 SAFETY item: pure logging -- changes no entry selection, no size, no exit rule.** Writers are heartbeat_core (core arms) + fleet_executor (fleet arms) -- both FROZEN, so this is built in a branch now and merged at the checkpoint, per work-order §3. :: depends:none :: status:pending
- [ ] PREREG-BACKLOG-ADJUDICATION (HIGH, work-order §2a, adjudicated 2026-09-02 Opus; 4 RUNS outstanding) :: `prereg_hygiene.json` (2026-09-01) reads **124 preregs, 0 malformed, 6 FLAGGED** (frozen + age>14d + orphan) and **20 at `FROZEN_PENDING_RUN`** -- note the work order said '15 frozen', the real count in that exact status is 20. All 6 flagged are SHAPE-CHANGE hypotheses, so none may SHIP before 10-30; all are runnable as MEASUREMENT, which is freeze-compatible. **Adjudication (Opus judgment; verdicts are the deliverable, the 4 RUNs are Sonnet work on existing harnesses):** **(1) `prereg-ladder-x-premium-2026-08-09` -> KILL.** Named nail: its own frozen text blocks it on 'the risky-3 forward result (prereg STOP-MODE-LIVE-ARM-RISKY3-2026-08-09)', and `accounts.json` has risky-3 at `status: retired, live: false` -- **the evidence it waits on can never be produced.** Re-open ONLY if risky-3 is un-retired. **(2) `prereg-pdt-blocked-counterfactual-2026-08-11` -> RUN FIRST.** Pure counterfactual, measurement-only, data already on disk (fleet decisions carry `pdt_enforced` / `day_trades` / `day_trades_true` / `risk_code`). Extra urgency: FINRA repealed the $25K PDT floor 2026-06-04 and the **Sat 09-05 Rule 7 doctrine edit** depends on knowing whether the engine's self-imposed PDT constraint COSTS or SAVES money. Highest value of the six. **(3) `prereg-recency-qty-clamp-2026-08-11` -> RUN.** Harness exists (`backtest/tools/multileg_exit_walk.py`, calibration v5). Well-specified: G1-G4 gates, explicitly forbids shipping on the linear-scaling estimate, and its own `sample_note` caps the outcome at 'licenses a forward paper trial, never a direct ship' (43 clamped positions over 7 days, below the n>=20 DAY bar) -- so running it CANNOT breach the freeze. **(4) `prereg-runner-finite-tgt-candidate-2026-08-06` -> RUN.** `exit_manager_walk` exists; tests finite 2.5x runner target vs today's 99.0 sentinel. Feeds the 10-30 shape-change menu directly. Cheap. **(5) `profit-lock-arm-scope-prereg-2026-08-06` -> RUN WITH A CAVEAT.** There is a KNOWN sim-vs-live profit-lock scope divergence (sim locks pre-TP1, live post-TP1); the runner MUST replay live semantics or the result is a harness artifact, not an engine result. After tonight's V9 episode that caveat is load-bearing -- validate the validator before reporting a verdict. **(6) `prereg-ladder-vwap-2026-08-11` -> PARK.** It optimizes the EXIT of a cohort whose own edge is unestablished and negative (VWAP_CONTINUATION -$1,046 n=34 flat_to_flat / -$1,114 n=45 fill basis) while the open WATCHER-LANE-PROVENANCE-AUDIT is still deciding whether that lane stays armed at all. Tuning a cohort that may be disarmed is polishing a corpse. **Re-open condition:** the watcher-lane audit KEEPs VWAP_CONTINUATION armed AND its cohort reaches n>=50. **Still to adjudicate:** the remaining 14 of the 20 `FROZEN_PENDING_RUN` entries (not flagged, so younger or non-orphan) -- same three-way verdict, no 'still frozen' survives the month per the work order.  **RUN 1 of 4 COMPLETE 2026-09-02: `prereg-pdt-blocked-counterfactual-2026-08-11` -> verdict `FAIL_PDT_STAYS_AS_IS`.** Population re-derived independently and matched the prereg exactly (68 attempts -> 18 unique intents, 2026-07-08..08-07, 9 days). Gates ALL fail: G1 net **-$11.20**; G2 2 profitable vs 7 losing days; G3 net-minus-best-day **-$1,390.50** (best day 08-04 +$1,379.30); G4 undefined on a non-positive net. Per the frozen decision rule PDT stays exactly as-is, filed as protective-or-neutral. Artifacts: `setup/scripts/pdt_blocked_counterfactual.py`, `analysis/recommendations/pdt-blocked-counterfactual-2026-09-02.{json,md}`, guard `test_pdt_blocked_counterfactual_2026_09_02.py` (28 tests, RED-proofed by flipping G1/G2 comparators). **Harness validated FIRST (the V9 discipline): sign agreement 95.35% on n=43 anchor rows, above the 85% bar** -- achieved precisely by honouring each row's RECORDED `stop_mode` rather than assuming structure, i.e. the same fix that lifted the whole-engine null's V9 from 79.3% to 89.3% the same night. **⚠️ CAVEAT THE RUNNER DID NOT DRAW OUT, added on review:** sign fidelity passed but MAGNITUDE did not -- the anchor set replays to **-$2,201.60 against an actual -$538.00** (median abs error $32.40), i.e. the walker is ~4x too negative in aggregate. That bias direction makes a blocked cohort look WORSE than it was, so the correct reading of this FAIL is **'PDT was not demonstrated to be costly'**, NOT 'PDT is demonstrated protective'. It does not rescue the result (G2's day-balance and G3's drop-best are not pure scale effects) but it bounds the claim, and it must be fixed before the remaining 3 RUNs are believed on magnitude-sensitive gates. Filed as `WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY`. **Feeds Sat 09-05:** the Rule 7 rewrite can proceed without pressure to relax the paper-side PDT simulation. **3 RUNs outstanding** (recency-qty-clamp, runner-finite-tgt, profit-lock-arm-scope) + the 14 unflagged FROZEN_PENDING_RUN entries.  **SCOPE CORRECTED 2026-09-02 (the work order's "15 frozen, never-run" understates it by ~3x).** Full count from `prereg-hygiene.json`: **42 preregs sit in a frozen/never-run status** -- `FROZEN_PENDING_RUN` 20, `FROZEN_PREREG` 4, `FROZEN_PREREG_FORWARD` 4, `FROZEN_BEFORE_ANY_RESULT` 4, `FROZEN_BEFORE_RUNNER` 3, `PRE-REGISTERED` 4, plus 3 with prose statuses. Only **6** are FLAGGED (the hygiene monitor flags only frozen + age>14d + **orphan**), and those 6 are the ones adjudicated above. **The other 36 are unflagged purely because something in the repo references them** -- note `prereg_hygiene.py:213` defines `orphan = f.stem not in referenced`, i.e. non-orphan means *a file mentions it*, NOT that a runner exists. Do not read non-orphan as runnable. **The striking shape: 20 of the 36 are 44-55 days old**, every one `FROZEN_PENDING_RUN` -- `headroom-retest`, `measured-move`, `structure-stop`, `vwapcont-matrix`, `block-elite-bull-ssb` (54-55d); `expected-move-gate`, `morning-gate` (53d); `trend-alignment-correlation`, `trendline-break-battery`, `trendline-fade-battery` (50d); `lbfs-shadow-wiring`, `directional-gate-battery`, `level-memory-wire` (49d); `favorable-extreme-entry`, `pong-resting-limit`, `regime-conditioned-validation`, `zone-rejection-band` (47d); `premarket-touch-credit`, `structure-stop-reference-level`, `structure-stop-zone-band` (44d). A hypothesis frozen 55 days ago and never run is not a pre-registration any more -- it is a to-do with good manners. **NEXT SESSION'S BOUNDED STEP (do not try to adjudicate 36 in one pass):** Sonnet fact-pack over the 20-item 44-55d cohort answering three questions each -- (a) does a RUNNER actually exist and does it execute, (b) is its dependency still alive (the risky-3 nail above killed one already), (c) is it a SHAPE change (10-30 only) or measurement (runnable now). Opus then gives each a one-line RUN / KILL-with-nail / PARK-with-reopen-condition. :: depends:none :: status:in-progress
  **THE REMAINING 8 `FROZEN_PENDING_RUN` ADJUDICATED 2026-09-03 01:17 ET (Fable; `prereg-hygiene.json` now lists 8, not 14 -- others resolved since 09-01).** **RUN now (measurement, freeze-compatible):** (a) `block-elite-bull-ssb-preregistration` -- real-fills cohort study of the bull-side elite block; the bull side is now the winner (core recency GREEN_CONCENTRATED n=38 +$49.55/tr) and blockers 6/10/11 were the binding constraint on 09-02, so this feeds the 10-30 shape menu directly; builder spawned. (b) `prereg-zone-rejection-band-2026-07-17` -- J's levels-are-zones doctrine as a trigger; runs on the existing mining harness; queued behind the walker-fidelity study (OPRA cache is single-reader). (c) `prereg-regime-conditioned-validation-2026-07-17` -- a METHOD prereg with a no-ship clause; its self-validation is exactly what the gate's calm-only-window weakness needs before 10-30. **RUN after the walker magnitude criterion lands:** (d) `prereg-directional-gate-battery-2026-07-15` -- gate ON/OFF A/B on dollar gates; not believable on size until WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY closes (in flight tonight). **PARK:** (e) `prereg-expected-move-gate-2026-07-11` -- a NEW blocking gate while participation is the disease (2/24 stress days, filter 10 blocking 74% of 09-02) points the wrong way; re-open only as a stratification column in the whole-engine null's regime coverage, not as a gate. (f) `prereg-pong-resting-limit-2026-07-17` -- execution-mechanism change; wait for EDGE-1-PASSIVE-LIMIT-GRADUATION's twin measurement. **DEAD (status lifecycle fixed in the files):** (g) `prereg-favorable-extreme-entry-2026-07-17` -> KILLED (its study ran and killed; status never updated). (h) `prereg-morning-gate-2026-07-11` -> SUPERSEDED by the 09-02 per-hour study. Still open in this item: RUNs 3/4 (recency-qty-clamp, runner-finite-tgt, profit-lock-arm-scope) pending the walker criterion.
  **CORRECTION 05:02 ET 2026-09-03 (Fable):** 'the bull side is now the winner' above overstates the recency read -- the instrument itself stamps it `GREEN_CONCENTRATED` / NOT ACTIONABLE (n=42, +$41.48/tr on 09-02, concentration-carried). The RUN decisions stand (they are measurements); the framing does not.
  **RUN (a) + (c) CLOSED 2026-09-03 01:37 ET -- and BOTH had already run.** (a) `block-elite-bull-ssb-preregistration`: the canonical runner `block_elite_bull_ssb_revalidation.py` completed 2026-07-10 16:10 (`block-elite-bull-ssb-revalidation.json`, real OPRA fills, n=28 elite events): SS-B total **-$3,873.60**, drop-top-1 **-$6,810**, OLD exit **-$560** -> verdict **KEEP, gate stays armed** (unblocking loses money on this population). Tonight's OPRA-free cross-check reproduces every countable field exactly; status -> RUN_COMPLETE_KEEP, hash resynced. (c) `prereg-regime-conditioned-validation`: ran 2026-07-17 (`693d21af`) EARNS_RIGHTS, reproduced clean tonight (`6ab1bc74`). **Third and fourth instances tonight of 'result exists, status never written back'** -- detector filed as PREREG-RESULT-EXISTS-STATUS-STALE. Remaining: (b) zone-rejection-band (OPRA cache), (d) directional-gate-battery + RUNs 3/4 after the walker fix.
  **RUN (b) CLOSED 2026-09-03 02:45 ET -- `prereg-zone-rejection-band-2026-07-17` -> KILL on both accounts** (full 8-Z grid x 2 accounts in 294 s on `exit_manager_walk`, the walker that PASSES the magnitude criterion, so these dollars are trustworthy): SAFE best cell fixed_0.3 2/5 gates n=3; BOLD best fixed_0.75 3/5 gates n=15, IS -$343/tr, OOS +$60/tr, BH-FDR survivor on NO cell. Exact-pierce `detect_level_rejection` stands. It had ALSO already run on 2026-07-17 with KILL (fifth status-never-written-back tonight); trade-count drift 139->138 / 191->192 traced to 15 params commits since, not nondeterminism. Results `zone-rejection-band-results-2026-09-03.{json,md}`, status RUN_COMPLETE_KILL, hash resynced, 19 tests. Remaining in this item: (d) directional-gate-battery + RUNs 3/4, all parked behind WALKER-MARKET-STAGE-FILL-ROOT-FIX.
- [ ] FLEET-KILL-SWITCH-NOT-LATCHED (**HIGH, Rule-5 doctrine gap on the prod-shadow arm**, kill-type risk reduction -> SHIP IN THE 09-29 SAFETY BUNDLE; found 2026-09-02 Opus fleet-path audit) :: **Rule 5 says 'Day closed for that account. No revenge trades.' On the FLEET arms -- safe-3 included, the arm criterion 5 and the whole 10-30 decision rest on -- nothing closes the day.** Verified cold, three legs: (a) `setup/scripts/daily_loss_guard.py`, the producer that durably sets `tripped=True` for the CORE accounts, has **zero** references to fleet / safe-3 / risky-1 / risky-3 (grep count 0) -- it maps only 'safe'/'bold'. (b) Fleet Rule-5 enforcement is instead a **live per-tick recompute** in `backtest/lib/risk_gate.py:750-755`: `kill_floor = sod_equity_f * (1.0 - kill_pct)`; `if equity_f <= kill_floor:` deny CODE_KILL_SWITCH -- whose own message reads *'day closed, no revenge trades'* while **persisting nothing**. (c) The only production writers of `tripped=True` are `daily_loss_guard.py:295` (core only), `eod_flatten.py:207` (escalation), and `halt_command.py:224/243` (phone HALT) -- **no fleet daily-loss path ever sets it**. **Consequence:** the block is a threshold, not a latch. equity = cash + position MARK, so an arm can breach -30% on an underwater open 0DTE position, be blocked, then have that mark recover above the floor and **silently resume entering the same session** -- exactly the revenge-trade sequence Rule 5 exists to forbid. Core arms cannot do this; they latch until premarket re-arm. **Calibration, measured not assumed (be honest about severity): 0 observed breaches to date** across all fleet decisions.jsonl history -- no arm has yet crossed its floor. Worst intraday equity draws seen: risky-3 **-24.4%** (within 5.6pp of the floor), safe-3 **-18.2%**, risky-1 -10.1%, safe-1 -5.7%. So this is **LATENT and REACHABLE, not yet exercised** -- and it converts from a paper defect into a real-money defect the moment anything is armed. **FIX (kill-type reduction, freeze-permitted at the checkpoint):** extend the durable latch to fleet arms -- either add them to `daily_loss_guard.py`'s ACCOUNTS map or have `fleet_live` persist `tripped=True` + `tripped_reason='daily_loss'` on the first breach, re-armed only at premarket like the core. Ship with a guard that RED-proofs the latch (breach -> recover -> assert still blocked).  **BUILT 2026-09-02 ON BRANCH `safety-bundle-2026-09-29` (commit `a632fb2c`) -- NOT on main, NOT merged.** The freeze permits kill-type risk reductions only at the 09-29 checkpoint, so this is §2d's "09-29 safety bundle prepared in a branch with tests". **Verified cold: `main` contains 0 occurrences of the new function, its working tree for `automation/state/fleet/` is empty-diff, and the branch carries exactly 2 files (`fleet_live.py` +75/-1, new test 305 lines).** **The obvious fix was a trap and was NOT taken:** adding fleet arms to `daily_loss_guard.ACCOUNTS` would build a latch that can NEVER trip, because `fleet_live._load_or_arm_breaker` writes `current_equity` only when arming fresh for the day -- if today's file exists it returns it unchanged, so `current_equity` is frozen at SoD and `max_drawdown_today_pct` stays 0.0 all day. A guard reading those would never fire, which is worse than no guard (it manufactures the belief something is watching). **What was built instead:** `_refresh_breaker_and_check_kill()` in `fleet_live.py`, called once per arm per tick at the one point that already holds fresh broker equity + the breaker + SoD. It (a) refreshes `current_equity`/`max_drawdown_today_pct` every tick so the file stops lying, (b) on breach and not already tripped persists `tripped`/`tripped_at`/`tripped_reason` (reason shape mirrors `daily_loss_guard.py:295-299` so both engines read alike) and returns `killed=True` for the SAME tick, (c) writes atomically and fails OPEN on OSError -- never crashes a tick, never blocks a trade on a failed write. Re-arm stays the existing date-rollover branch; no second re-arm path. `risk_gate.py` untouched (frozen) and remains the independent second layer. **The 2026-08-10 scar is pinned:** the exit path is byte-identical -- `exit_pass = ea.manage_tick(..., live=bool(master_live) and bool(arm.get('live')), ...)` carries no `killed`/`tripped` term, verified on the branch, and a test pins it. **Guard:** `backtest/tests/test_fleet_kill_switch_latch_2026_09_02.py`, 8 tests, **8 passed**; RED-proofed by stashing `fleet_live.py` -> 6 failed / 2 passed (the 2 that pass pin pre-existing exit-gating). The load-bearing case `test_latch_survives_equity_recovery` breaches at -35%, **re-reads the breaker from disk** (proving persistence, not in-memory state), recovers to -5%, and asserts still killed. Regression: kill-switch/settlement suites 55 passed; `test_fleet_*` 181 passed. **MERGE AT THE 09-29 CHECKPOINT, not before.** :: depends:none :: status:built-awaiting-09-29
- [ ] EARLY-CLOSE-CALENDAR-AWARENESS (HIGH, post-freeze ~09-29, HARD DEADLINE before 2026-11-27) :: Live broker calendar (verified 2026-09-01): 2026-11-27 and 2026-12-24 close 13:00 ET. Nothing in the stack knows: `heartbeat_core._is_rth` is `weekday()<5 and 9.5<=h<=16.0` (first line of main(), frozen file); entry cutoffs 09:35/15:00, time stop 15:40, Core flatten 15:52, LLM flatten 15:55 are fixed clocks; Task Scheduler triggers are plain Mon-Fri; `engine_health._refresh_calendar_from_alpaca` fetches `close` and DISCARDS it. Fix: persist per-date `close` in calendar.json; make _is_rth / entry cutoff / time stop / flatten calendar-relative (flatten >=30 min before actual close, block entries >=90 min before). Invisible in paper (no physical settlement); on real money an ITM 0DTE past 13:00 auto-exercises into ~$77K of stock per contract. **FLATTEN HALF SHIPPED 2026-09-01 (TASK B2, no frozen file touched):** `automation/state/calendar.json` now carries `early_closes:{date:'HH:MM'}` alongside the existing `holidays[]` (shared writer: new `setup/scripts/market_calendar.py`, both `engine_health.py` and `eod_flatten.py` import it); `eod_flatten.py --only-if-early-close` (new `Gamma_EodFlattenEarlyClose` task, weekdays 12:32 ET) checks today's close (cache first, live `/v2/calendar` GET fallback), NOOPs on a normal 16:00 day, fails CLOSED (no action) if the calendar state is unknown either way, and runs the identical sweep as `Gamma_EodFlattenCore` once `now_et >= close-30min` on a genuine early close -- covers 2026-11-27/12-24 today, ahead of the 11-27 deadline, independent of the frozen entry-side fix. `engine_health.py` also gained a non-critical `early_close_today` visibility check. Guard: `backtest/tests/test_early_close_flatten_2026_09_01.py` (10/10, RED-proofed). **STILL OPEN (needs 09-29):** the entry-cutoff half (`_is_rth` / 09:35 entry gate / 15:40 time stop going calendar-relative) -- all four live inside frozen `heartbeat_core.py`; status stays pending on that half only. :: depends:none :: status:pending
- [ ] TIME-STOP-BROKER-SWEEP (HIGH, kill-type risk reduction, prereg FILED `analysis/recommendations/prereg-time-stop-broker-sweep-2026-09-01.json`, ship at freeze close 09-29 -- NOT mid-window) :: Alpaca's options policy (doc fetched 2026-09-01): from 15:30 ET on expiry day it liquidates expiring ITM longs the account cannot exercise ('while it's still ITM'; 'slightly OTM may also be liquidated'). Our time_stop_et=15:40 and every flatten fire AFTER that. Change time_stop_et 15:40 -> <=15:20 on both params files per the prereg; log/reconcile OPEXC/OPASN/OPEXP activities (zero handling exists today). :: depends:none :: status:pending **MEASURED 2026-09-01 (wave 2, B6): [15:20,15:40] band = 0.00% of post-08-11 gross winner dollars; prereg verdict SHIP; give-up at 15:20 measured -$294 over 16 open positions; 5 positions ITM/near-ATM at 15:30 (sweep exposure). Ships at the 09-29 safety checkpoint, not mid-window.**
- [x] PHONE-HALT-COMMAND (HIGH, go-live prerequisite, new capability) :: BUILT 2026-09-01 (TASK B5-phone-halt): `setup/scripts/halt_command.py` (new module, imported by discord-responder.py) parses `HALT <arm>` / `HALT ALL` / `HALT <arm|ALL> FLATTEN` / `RESUME <arm>` from an allowlisted author (J's Discord user_id, same identity discord-responder.py's main() already filters the inbox to). CORE arms (safe-2/bold-2): trips the account's OWN circuit-breaker.json (tripped=true + escalation_unresolved=true), enforced by heartbeat_core's existing entry-gate read within 1 tick. FLEET arms (safe-3/risky-1): trips `automation/state/fleet/<arm>/circuit-breaker.json` -- CORRECTED FINDING vs this item's original framing: that file (not `kill-switch-<arm>.json`, which nothing reads) IS read every tick by fleet_live.py's `_load_or_arm_breaker` and gates `arm_live`, so a fleet-arm HALT blocks new entries within 1 min (next Gamma_FleetExecutor tick) -- `kill-switch-<arm>.json` is still written too, for audit parity with eod_flatten.py's own escalation precedent, but is NOT the enforcement path. FLATTEN reads positions via `fleet_broker.open_spy_option_positions_checked` and refuses (does not act) on a failed read; only submits `close_all_spy_options(..., live=True)` on a confirmed-open read. RESUME clears `escalation_unresolved` only (tripped left as-is; rule 9). Every HALT/RESUME/FLATTEN + every refusal logged to `automation/state/logs/halt-<date>.log` and to STATUS.md's `## Live watch` section. Tests: `backtest/tests/test_phone_halt_2026_09_01.py` (52 passed), RED-proofed (inverted the FLATTEN fail-closed guard -- a failed read then wrongly read as NOOP_ALREADY_FLAT instead of ABORT_READ_FAILED; 2 tests failed as expected; reverted, 52/52 green again). NOT YET DRILLED: needs an actual phone->Discord->inbox->responder round trip with the responder task enabled (it is currently quiet-mode-disabled, self-restoring ~23:00 ET tonight per `quiet-mode-restore.json`) plus a broker-verified before/after on a real paper position -- LIVE-FLIP-RUNBOOK §2 item 8 stays UNCHECKED until that drill runs. ALSO FLAGGED (not fixed here, separate follow-up filed): `Gamma_DiscordResponder`'s own scheduled-task trigger only fires 16:00 ET-~09:30 ET (after-hours) -- during RTH (09:30-15:55 ET, exactly when an emergency halt matters most) the task does not fire at all today, so a phone HALT sent mid-session would sit unprocessed until the next after-hours tick. :: depends:none :: status:built-not-drilled
- [ ] HEARTBEAT-PIDFILE-MUTEX-AND-VBS-FIX (HIGH, post-freeze 09-29, touches frozen heartbeat_core.py + run-heartbeat-core.ps1) :: Gamma_HeartbeatCore's registered action is `wscript run_exe_hidden.vbs pythonw run_ps1_hidden.py run-heartbeat-core.ps1` and the vbs does `shell.Run cmd,0,False` (fire-and-forget), so MultipleInstances=IgnoreNew / ExecutionTimeLimit=PT1M measure wscript's millisecond lifetime, not the engine (L275 named this task and deferred the fix; L277 same class). Overlapping ticks are ledger-proven (3 distinct core_tick_id inside one minute on 2026-08-11; the -$371 duplicate-entry incident 08-14 produced the ENTRY claim-lock `_acquire_claim`). EXIT management has no lock. Fix: pidfile/mutex around main() exit pass (fail-open on read errors), and register the task without the fire-and-forget hop (or fix the vbs to wait). Interim: DUPLICATE-TICK-MONITOR below. :: depends:none :: status:pending
- [ ] SIP-VOLMULT-MISMATCH (**RAISED to HIGH 2026-09-02 -- now has a live worked example, was theoretical**) :: **2026-09-02 is the case study: the day's own thesis played out and the engine took nothing.** Premarket called 'SPY breaks and holds above 763.16, extending toward 764.30-765.12'; SPY ran 762.39 -> 766.31 (+0.4%) inside the 09:35-12:00 window, ribbon went cleanly BULL. The engine AGREED -- `bull_score` max **10**, median **9**, **92 of 178 ticks scored >=9**, with `level_reclaim` firing 78x and `confluence` 78x, so blocker 11 (the trigger requirement) was SATISFIED. **Blocker 10 fired on 144 of 178 ticks and was the binding constraint.** Blocker 10 = `buyer_pressure_bar_v11` (`filters.py:1366`): green bar AND `volume >= f10_vol_mult * vol_baseline_20`, with `f10_vol_mult=0.7` **ratified on SIP volume and running on IEX** (~3.6% of SIP). All four arms finished the day flat; zero option fills. **DO NOT change the threshold on this alone.** Evaluating filter 10 against today's raw IEX 5m bars with an APPROXIMATE 20-bar baseline showed the volume condition PASSING on most bars (0.85x, 1.56x, 1.30x, 1.40x) -- which does not reproduce 144 blocks, so the engine's own `vol_baseline_20` is computed differently from that approximation and the REASON it binds is unproven. Two candidates to separate first: (a) the IEX/SIP mismatch biases or adds noise to the ratio; (b) the baseline window spans sessions and is inflated. **DO:** log `vol_baseline_20` and `bar.volume` on every tick (they are not in the decision row today -- that absence is itself the reason this took a reconstruction), then compare the same bars on IEX vs SIP, and only then re-derive `vol_mult` on the feed it actually runs on. Note filter 10 is a RATIO, so a uniform feed-share difference largely self-normalizes -- the suspicion is bias/noise, not simple scaling. :: depends:none :: status:pending
  **RESEARCH DONE 2026-09-03 01:10 ET (Sonnet, Fable-specced) -- `analysis/entry-quality/SIP-VOLMULT-2026-09-02.md`, runner `backtest/tools/f10_volume_reproduce.py --date`.** Baseline traced in BOTH engines (`filters.py:131` / `heartbeat_core.py:928`): 20-bar trailing mean over a continuous RTH-only multi-day series, NO per-day reset, so 09:35-~11:15 bars borrow the prior day's tail. Reproduction on the REAL filter functions: 144/178 were TICK counts; by bar the live engine blocked 57/77 (74%), replay SIP 55/77, IEX 58/77 -- reproduced within 2-3 bars. (a) IEX/SIP bias is NOT the cause: with same-day baselines both feeds block the identical 50/77 bars; ratio correlation 0.77. (b) session-spanning baseline is REAL but adds only ~6-10pp on top of a 65% same-day base rate. Verdict: the day traded under 70% of its own trailing volume on both feeds -- the filter did what it was ratified to do on a low-turnover day; NOT a bug, NOT a threshold change. Decision row still carries no `vol_baseline_20`/`bar_volume` field (frozen file; add as a logging-only field in the 09-29 safety bundle). Candidate for a 10-30 prereg, not before: per-session baseline reset (shape change). n=1 day for the feed comparison, 4 days pulled. :: status:research-done
- [ ] WEEKLY-CIRCUIT-BREAKER-CORE (MED) :: **PREREG FILED 2026-09-02, and the in-sample answer is a NULL -- no ship is proposed.** Commit `3401e5fe`. The GAP is real: Rule 5 is per-DAY and the 08-18 day-throttle prereg already showed it unreachable (worst arm-day -24.4% vs a -30% floor); nothing in the core path looks ACROSS days, and real 3-day rolling losses reach -$640/-$955/-$1,306/-$1,214/-$1,252 across the five arms on ~$5,000 accounts. But the obvious fix is REFUTED: over an 8-cell grid (W=3,5 x T=$400..$1000) **every cell cost the book money** (-$53..-$1,718) and **6 of 8 made the worst per-arm drawdown DEEPER**. Mechanism verified on a named case: safe-3 lost -1048/-156/-102, tripping a 3-day/-$1000 circuit, and the NEXT session was +457 -- the circuit blocks the rebound. Corroborated by the window table (safe-3 10-day worst -482 vs 3-day worst -1306: drawdowns mean-revert in this record). W5/T800 and W5/T1000 are frozen for FORWARD evaluation only, with the load-bearing caveat disclosed: at W5/T1000 the entire +$133 comes from risky-1 blocking ONE day (2026-08-12), and W5/T800's gain clusters on 08-12..08-14 -- one mid-August event, prior is noise. **NOT a kill:** the record contains no regime where a drawdown failed to recover, so it cannot speak to the case a circuit is for. NEXT ACTION is at 2026-10-30, not 09-29: re-run `setup/scripts/rolling_loss_circuit_study.py` and judge the same 8 cells against the promotion bar frozen in the prereg (>=3 independent trip episodes on non-adjacent dates; per-arm positive dd improvement; cost < improvement). If unmet, log the null and close -- do NOT re-cut the grid. :: depends:none :: status:frozen_prereg_forward
- [ ] RULE-9-DOC-PASS-2026-09-05 (HIGH, Saturday 09-05, doctrine text) :: CLAUDE.md:65 -- arming = go-live criterion 5 (designated prod-shadow profile on the frozen window, all three views, net of A1 costs) + criteria 2-4; criterion 1 stays lifetime-robustness disclosure; one governing clock = 2026-10-30. Also: Rule 7 PDT text (FINRA repeal), Goal line ('both accounts grow' vs one live account), 'tp1_qty_fraction 0.8/0.667' (shadowed by strategies.py 0.667 both), 3x 'decisions.jsonl' -> core-decisions.jsonl. CHANGELOG row. Revoke = git revert. :: depends:none :: status:pending
- [ ] FUTURES-BROKER-CONNECT-FAILURE-RATE-ROOT-CAUSE (MED, filed 2026-08-30 conductor-weekend, follow-on to the diagnosability fix in commit `7147a115`) :: `Gamma_FuturesBrokerLane`'s connect-failure rate climbed 5% (08-11..08-21 baseline) -> 76% (08-28) per `trader-broker/decisions.jsonl` `connected` field, all classified `reason="broker_not_connected"` with zero recoverable detail (fixed THIS fire: `connect()` now sets `last_failure_detail` + logs a `broker-transport.jsonl` row for both transport and non-transport failures; ledger row now carries `connect_failure`). **Root cause is NOT YET confirmed** -- a manual interactive `connect()` succeeded cleanly 6/6 times tonight (Sunday, CME closed, no concurrency), so this is NOT a dead/revoked credential. Leading hypothesis (unconfirmed, do not act on it without evidence): `install-futures-broker-lane.ps1`'s `-MultipleInstances IgnoreNew` only guards the DIRECTLY-launched `wscript.exe` action -- the real work happens 3 hops deeper (`wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py -> venv pythonw -> futures_trader_runner.py`), so Task Scheduler considers the "instance" complete the moment `wscript.exe` exits (fire-and-forget), NOT when the grandchild Python process actually finishes. If a tick's real work occasionally runs past the 5-minute cadence under RTH sandbox load, two `TastytradeBroker.connect()` calls could race on the SAME `TT_REFRESH` token -- a well-known OAuth footgun where a concurrent refresh-grant request can invalidate the other with a non-transport `invalid_grant`-class error, which is exactly the failure signature here (never a 5xx/timeout, always an auth-layer rejection; `broker-transport.jsonl` was empty because until this fire's fix, non-transport connect failures were never logged at all). **NEXT STEP (do not guess further):** wait for Monday's real RTH connect failures to land with the new `connect_failure.error_class`/`error_repr` populated (this fire's fix), then read the actual exception text -- `invalid_grant`/`Session.__init__` conflict confirms the overlap hypothesis, anything else (5xx under a different label, a genuine account-side lock) points elsewhere. Only THEN consider a fix (e.g. a lockfile keyed on the grandchild PID, or caching+reusing one `tt.Session` across the token's 900s lifetime instead of minting a fresh one every tick). :: depends:none :: status:pending
  **UPDATE 2026-09-03T01:xx ET (conductor):** real evidence now exists (28 rows, `broker-transport.jsonl`, 08-31..09-02). The `invalid_grant`/OAuth-race hypothesis above is **REFUTED** -- 0/28 rows show it. The `invalid_price_increment` scar is **CONFIRMED FIXED** (0 occurrences since 08-31, matching `futures_trader_core.py`'s own tick-rounding fix). Remaining: 502/ReadTimeout (already retried 3x via `_with_retry`, vendor-side reliability, not obviously further actionable) + a NEW class, `"User is not a TastyTrade customer"` (5x since 09-01) that was being silently misclassified as generic transport noise -- FIXED this fire (commit `373e251b`, `_is_transport_error` now distinguishes a structured `error_code` broker answer from real gateway noise; logs `auth_or_permission_error` instead). Full evidence + fix detail: STATUS.md 2026-09-03T01:xx ET entry. Still open: WHY "User is not a TastyTrade customer" happens at all (now visible/fails-fast instead of buried; next session should watch for fresh `auth_or_permission_error` rows and read the account/session context at that exact timestamp).
  **EVIDENCE 03:43 ET 2026-09-03 (Sonnet, read-only):** all 5 `User is not a TastyTrade customer` rows (09-01/09-02) cross-referenced with `run-cmd-hidden-2026-09-01.log`: strictly sequential launches (10:40 pid 30264 exits 10:40:04; 10:45 pid 24736 starts 10:45:00, 15 s for 3 backoff retries) -- no grandchild overlap; the mirror lane's `connect()` was never invoked at any of the 5 timestamps (`mirror-broker-orders.jsonl` empty there). Both client-side race hypotheses are ruled out; what remains is an intermittent sandbox-side rejection (~5 in 3 days, self-resolving on the next 5-min poll), consistent with the cert sandbox's documented 24 h resets. Further progress needs vendor-side logs. Left open as a watched count, not a bug to fix. :: status:pending

- [ ] DAILY-PREMIUM-BUDGET-J-CALL (HIGH, **J JUDGMENT CALL - built, battery-run, ships OFF**, filed 2026-08-28 ~14:30 ET interactive, J-directed from â€œhow do we spend less and still hit targetâ€) :: **Finding:** over 42 days the book deployed **$141,641** of premium to net **+$1,317** (0.93% ROI, net of A1 fees). **48% of all 427 entries (205) were placed while that arm was ALREADY RED on the day.** Two policy overlays tested on the T1 broker-truth tape (subtractive - entries are only ever REMOVED, never resized, so no counterfactual price paths): **A_flat** (cap from the first entry) and **C_loss_armed** (cap binds only once the arm books a losing exit that session). **C @ $700/arm/session: net +1317 -> +5161 (+3844) on $87,744 vs $141,641 deployed (62% of the capital); maxDD 4,908 -> 2,544; PF 1.0846 -> 1.5093; worst day -2694 -> -1573.** Per-arm: risky-3 -590->+1310, safe-2 -233->+952, safe-3 +824->+1723, bold-2 +309->+344, risky-1 +1257->+1084. **WHY IT DOES NOT AUTO-RATIFY (OP-11 needs all four):** C passes oos_positive (+2536 on 17 OOS days), sub_window_stable (all 3 windows +), and anchor_no_regression (-5.3% on the 5 best realised days) - but **FAILS wf_median_ge_0.70** (median -0.0676, folds [1.0, -0.0676, -0.8921]). A_flat is the mirror image: passes WF, **fails anchor at -32.3%** - a flat cap trims size on exactly the trend days the right-tail edge lives on, which is the whole reason C exists. **Honest read:** WF here is 3 folds of 5 trading days on a 42-day sample; the scorecard already discloses WF as corroborating-not-decisive at this n, and A_flat's â€˜passâ€™ comes from two folds clipping to 1.0. C's failure is on the weakest metric; A's is a real economic regression. NOT hand-waving the gate - the rule ships OFF. **STATE: code merged, rule INERT.** `check_daily_premium_budget()` in `backtest/lib/risk_gate.py` returns None whenever `params.daily_premium_budget_dollars` is absent (it is). Guard `backtest/tests/test_daily_premium_budget_2026_08_28.py` 25/25 pins the off-by-default property FIRST; `test_risk_gate.py` 96/96 + 58 consumer tests confirm byte-identical behavior. **TO ARM (one params edit, after-hours only - Rule 9):** add `"daily_premium_budget_dollars": 700` (and optionally `"daily_premium_budget_loss_armed": false` for the flat shape) to each arm's params. **J's call is:** arm it now on 3-of-4 + the mechanism argument, or hold until WF clears on more data. **Recommendation: arm it on risky-3 and safe-2 first** (the two arms it flips from negative to positive) and leave risky-1 alone (-173). Scorecard: `analysis/recommendations/daily-premium-budget.json`. Battery: `backtest/autoresearch/daily_premium_budget_battery.py`. Prior coverage read first: B3-loss-anatomy, B3-bounded-config, A1-cost-rebuild (all 2026-08-28). **Revalidation clock (J recency doctrine): re-run the battery weekly; if WF clears with more OOS days, this becomes auto-ratifiable without a new judgment call.** :: depends:none :: status:awaiting-J
- [x] GAMMA-PREMARKET-SELF-HEAL-WINDOW (MED, filed 2026-09-03 03:14 ET from SINGLE-FIRE-TRIGGER-BLANKET-AUDIT) :: `Gamma_Premarket` (08:30 ET, trading-critical: today-bias.json, circuit-breaker.json) is the last single-daily-fire producer feeding a freshness consumer WITHOUT a retry window (`Export-ScheduledTask` 03:20 ET: CalendarTrigger, no Repetition). It has no isolated install script (registered by the shared `harden-tasks.ps1`/`fix-trading-tasks.ps1`). Before adding `PT15M/PT30M`: verify the premarket script is idempotent on a second fire within 30 min (a 08:45 re-run must not overwrite a good 08:30 bias or re-seed the journal) -- add a done-marker skip if it is not -- then give it its own `install-premarket.ps1`, register, quote the XML, add the task name to the new guard's expected set. After-hours only (touches the morning chain). :: depends:none :: status:done -- SHIPPED 18:40 ET 2026-09-03: script was NOT idempotent (fresh $3 LLM call, full rewrite of today-bias.json, journal overwrite) -> done-marker skip added (fail-open, DST-aware ET mtime check, 5 tests); setup/install-premarket.ps1 registers the same Exec with PT15M/PT30M; export diff = trigger block only; State=Ready, NextRunTime 2026-09-04 08:30 ET; guards 10 passed. First real self-heal behaviour UNVERIFIED until a missed morning.
- [ ] FLEET-STRIKE-TIER-ATM-EXTENSION-EVAL-2026-08-01 (MED, engine-participation, follow-up, dormant -- see 2026-08-27 verdict) :: Filed 2026-08-01 (conductor, AFTERHOURS) as the evaluation half of FLEET-STRIKE-TIER-ATM-EXTENSION (see COMPLETED). risky-1/risky-3 are now armed on `V15_BOLD_CORE_TIERS` (ATM under $2K) per the pre-reg `analysis/recommendations/fleet-strike-tier-atm-extension-prereg-2026-08-01.json`. NOT READY until n>=20 real fleet fills (risky-1+risky-3 combined) accumulate dated on/after 2026-08-01. When ready: score the 5 frozen gates in that JSON (oos_positive, walk_forward_or_disclosed_null, sub_window_stable, anchor_no_regression, premium_floor_clearance-informational) into a proper scorecard at `analysis/recommendations/fleet-strike-tier-atm-extension-2026-XX-XX.json`; re-run a `min_entry_premium_blocked_replay_2026_07_31.py`-style funnel audit scoped to these 2 arms' post-arming dates to confirm SKIP_MIN_PREMIUM_FLOOR refusals actually dropped. If gates FAIL: revert is one line per arm (delete `strike_tier_table:'bold_core'` from `accounts.json`'s risky-1/risky-3 `params_patch`). :: depends:none :: status:pending

> **VERDICT 2026-08-27T01:10 ET (conductor AFTERHOURS): DISCLOSED_NULL_STRUCTURALLY_UNREACHABLE -- NOT a kill, item downgraded to DORMANT.** The raw "n>=20 combined fills" text looked satisfied (139 total: 73 risky-1 + 66 risky-3) and `task_scorer.py` correctly read it as `ready`, but scoring it would have been wrong: risky-1's 73 fills are 100% `FULL_SEND`-lane (per the prereg's own 2026-08-02 addendum, PROVABLY INERT to `strike_tier_table` -- confirmed again live), and BOTH arms' `equity` field on every single named-setup decision-row since 2026-08-01 (504 risky-3 rows, 607 risky-1 rows) sits in the **2K-10K** bracket -- never the **0-2K** bracket this specific prereg's code change touched. n=0 mechanism-relevant fills exist. All 66 of risky-3's real fills were actually priced by the (separate, already-adjudicated) 2K-10K row governed by `atm-tier-extension-2k10k-prereg-2026-08-03.json`, already killed for risky-3 on 2026-08-06 (commit `3ac1d7b2`) -- scoring this item against them would have double-counted that closed decision under the wrong rule_id. One near-miss checked and ruled out: risky-1 briefly logged equity=$1,756.87 on 2026-08-01, but zero named setups fired that day (weekend, arming landed after Friday close) before the "$5,000 account rebuild" pushed both arms back over $2K by Monday 08-03. **Corrected readiness criterion (replaces the raw fill-count one above): re-check ONLY if either arm's logged `equity` drops back below $2,000 on a live decision row** -- given both arms sit near $5K and have shown no sustained drawdown toward that floor, treat this as dormant, not actively accruing evidence; stop re-surfacing it as an in-progress item until that condition is met. **NO REVERT** -- nothing has fired, so there is nothing to undo. Full derivation + gate-by-gate scoring: `analysis/recommendations/fleet-strike-tier-atm-extension-2026-08-27.json`. Generalizable lesson filed: `strategy/candidates/_lesson-inbox/sample-floor-gate-must-scope-to-mechanism-not-total-fills-2026-08-27.md` (any "n>=N fills since arming" gate needs a condition predicate, not a raw total-fill count, or it can look ready while measuring the wrong population).

> **INTERIM AUDIT 2026-08-02 (Sonnet, day+1, NOT a closure).** Routing re-verified direct from source (not the commit message): `_tiers_for_arm` resolves `V15_BOLD_CORE_TIERS` for risky-1/risky-3 via `strike_tier_table='bold_core'`, `V15_BOLD_TIERS` for safe-3 (byte-identical, unedited). Guards re-run fresh: 42/42 PASS across the 3 touched test files, and both bold_core assertions use `is`/`is not` identity checks in BOTH directions (safe-3 excluded correctly, risky-1/risky-3 included correctly) -- genuine C14 vary-and-assert, not incidental green. Live equity re-verified: safe-3 $1,967.81, risky-1 $1,756.87 (both <$2K), risky-3 $2,121.61 (>$2K). **Only risky-1 changes behavior today** -- risky-3's $2K-10K bracket resolves OTM-2 under EITHER table, so bold_core is currently a no-op there (re-audit if its equity drops back under $2K). Correction to a working assumption: risky-1's `full_send` lane is a fallback, not primary -- `plan_all()` evaluates the normal tight-gated lane (which uses bold_core) FIRST every tick, so this is a live, first-priority change, not a rarely-touched path. **n>=20-fill gate genuinely UNSTARTED**: ship landed Fri 07-31 23:13 MT after close; Sat/Sun are non-trading; zero fleet fills exist under bold_core as of this audit -- confirmed by calendar arithmetic. `bold_fullhist_replay.py` (the tool suggested for re-measurement) was found NOT fleet-arm-faithful for this question -- it hardcodes bold-2's OWN gate profile (aggressive/params.json), not risky-1's tight or risky-3's loose+hard-skip-bypassed gate_override, so running it would silently misrepresent either arm (OP-16 sim-accuracy gap, disclosed rather than papered over). Material counter-precedent surfaced: `full-send-arm-2026-07-31.md`'s real-OPRA A/B moved a comparable low-conviction fleet cohort from OTM-2 to ATM and P&L went +$3,430 -> -$5,110 full-population / +$118 -> -$1,088 recent-25 on a near-flat trade count -- direct evidence in this repo that nearer-strike participation gains don't reliably mean better P&L for a marginal cohort. Does not, alone, justify reverting an armed paper/guard-tested experiment with zero fills yet, but argues for an early-warning read at n>=5 (recommended, not applied -- the frozen pre-reg's gates are not reopened here) ahead of the existing n>=20 decision gate. **Verdict: NO REVERT. Item correctly stays status:pending -- still blocked on real fills, not yet scoreable.** Full writeup: `analysis/recommendations/fleet-strike-tier-atm-2026-08-02.{json,md}`.

> **CORRECTION (Sonnet, 2026-08-02, later same night, instrumented dry-run + git-blame verified).**
> The INTERIM AUDIT directly above is WRONG on one factual claim: risky-1's normal lane is
> NOT "tight-gated (min_triggers=2 + confluence/sequence required)". Commit `e28d210c`
> (2026-07-31 16:21, the FULL-SEND ship) REPLACED risky-1's whole `gate_override` with
> `{"full_send": true}` -- it did not layer full-send under the old tight gate. This was
> ALREADY on record hours before the audit ran: `FLEET-PARITY-TESTS-READ-LIVE-STATE`
> (commit `dea5b2e2`, ~02:00 ET the same night) independently rewrote a stale test with the
> explicit note "risky-1 ... its normal lane is now UNGATED same as risky-3." Likely cause:
> `accounts.json`'s `grid.map` metadata still read `"risky-1": "risky x tight"` (never
> updated when full-send armed, even though the arm's own `cell` field already said
> `"risky x FULL-SEND"`) -- fixed this session (`grid.map` corrected + `map_doc` added).
> **Corrected composition, empirically proven via `setup/scripts/risky1_lane_composition_check.py`**
> (real `fleet_executor.plan_all` + `build_shared_signal.build_from_rows`, not code-reading):
> risky-1's normal lane is UNGATED (no min_triggers/confluence bar left) and now prices ATM
> via `bold_core` for ANY passing signal, same population class as risky-3/bold-2's own
> entries. At risky-1's current equity (<$2K) this NUMERICALLY happens to match the
> FULL-SEND lane's own `PROBE_STRIKE_TIERS` pricing (both ATM) -- but this is an
> EQUITY-CONTINGENT COINCIDENCE, not a structural guarantee: the two tables' $2K-10K
> bracket diverges (`bold_core`->OTM-2, `PROBE_STRIKE_TIERS`->stays ATM), verified directly
> by sweeping equity through both `pick_tier` calls. The two lanes stay POPULATION-DISJOINT
> (`passed_full_send` requires an `action` on the 5-verdict allowlist, mutually exclusive
> with a normal "passed" tick) and separately TAGGED (`EntryPlan.reason` starts with
> `FULL_SEND` only for that lane -- the same tag `full_send_vs_gated.py`'s `_lane()` already
> parses), so **per-fill attribution between the two 07-31 experiments is NOT actually lost**
> -- what was missing is that this prereg's own evaluation methodology never said to keep
> them separate. Addendum filed on the prereg JSON (`lane_scoping_addendum`, frozen before
> any fills exist) requiring risky-1's future bold_core scorecard to EXCLUDE
> `reason`-prefix `FULL_SEND` fills from its own n>=20 cohort (bold_core is provably inert
> on those fills -- `_full_send_plan` never calls `_tiers_for_arm`), and vice versa for any
> full-send-specific re-check. **ADDITIONAL FINDING surfaced by the same instrumented
> check (flagged, not fixed -- out of scope tonight):** risky-3's own `gate_params.
> hard_skip_verdicts: []` rescue (built 2026-07-23 specifically so risky-3 could trade
> through `require_bearish_fill_bar`) is empirically DEAD on the live path -- `fleet_live.py`
> calls only `plan_all`/`_plan_from_strategies`, which never calls `_effective_passed` (the
> function that reads `hard_skip_verdicts`); confirmed by a live `SKIP_BULLISH_FILL_BAR_AT_
> BEAR_ENTRY` tick at a score above risky-3's own peak still holding it, while risky-1's
> full-send lane enters the identical tick. Guards: `automation/state/fleet/
> test_risky1_lane_composition_check.py` (9/9 green, RED-proofed on the grid.map fix).

### ZERO-FOR-TWELVE-POSTMORTEM (HIGH, filed 2026-07-25 with the disarm)

- [ ] ZERO-FOR-TWELVE-POSTMORTEM (HIGH) :: vwap_continuation (7tr, 0% WR, -$204) and
  vix_regime_dayside (5tr, 0% WR, -$153) were DISARMED 2026-07-25. Both were armed on 8/8-gate
  backtests claiming +$32-79/tr. **0-for-12 combined at a claimed ~55-64% WR is p<1%** -- that is
  a falsification of the VALIDATION PIPELINE, not two unlucky setups, and it is the single most
  important research question open. PRIME SUSPECT (already escalated separately):
  EXIT-ENGINE-ENTRY-BAR-CONVENTION-AUDIT -- replay engines disagree by $39.71/tr on whether the
  ENTRY bar's own high/low is eligible for stop/TP1 (simulator_real.py:534-535 starts the exit loop
  at entry+1; the bar-replay family starts AT the entry bar). That is exactly the sign and
  magnitude that would turn a +$32/tr paper cell into a live loser. ALSO CHECK: both cells' own
  arm-time caveats were written down and armed anyway (n=18-21 OOS; params.json carries an
  "L174 NOT INDEPENDENT / lift is largely day+side selection" note). DELIVERABLE: which convention
  is faithful to live risk, and a re-scored list of every currently-armed setup under the correct
  one. Until then, treat every "+$X/tr OOS" arm-time claim as suspect. depends:none :: status:CLOSED (2026-08-02 -- both threads closed, see PROGRESS notes below: entry-bar-convention ruled 2026-07-25, historical-OOS day-cluster closed 2026-08-02, 94.1% overlap confirms the L174 caveat and reframes the 0-for-12 as N<<12 independent trials)

> **PROGRESS 2026-07-25 ~17:45-18:15 ET (conductor, AFTERHOURS/weekend).** The
> EXIT-ENGINE-ENTRY-BAR-CONVENTION-AUDIT escalation was already RULED by the time this fire
> picked the item up (see `markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md`): entry+1
> IS live-faithful, no migration needed -- **this PARTIALLY EXONERATES the prime suspect** (the
> ruling's own words: "must NOT close on entry-bar convention explained it"). The ruling named
> the real next suspect: `engine_fullhist_replay`'s ENTRY-layer divergence (2 replay entries vs
> 4 live on 07-17, matcher paired on strike+side alone -- matched an 11:40 live fill to a 13:55
> replay entry, 2h15m apart). Picked that up and CONFIRMED + CORRECTED it this fire:
>
> - **Reproduced the raw entry divergence directly** (`lib.orchestrator.run_backtest` for
>   2026-07-17): the batch engine fires only 2 raw signals that day (13:15 P746, 13:55 P745) vs
>   4 live fills (11:06 P744, 11:40 P745, 13:01 P746, 14:49 P743) -- confirms the entry-layer gap
>   is real, not a reporting artifact.
> - **Found + fixed a REAL bug in the anchor-matcher itself** (separate from, but compounding,
>   the entry-layer gap): `engine_fullhist_replay.py`'s sanity-anchor `match_entries` paired
>   expected-vs-replayed entries on strike+side ALONE, no time bound, first-hit-wins -- so it
>   silently accepted the 11:40->13:55 pairing (2h15m apart, a genuinely different signal that
>   happened to share strike+side) as a PASS, reporting "2/4 matched" when the true, time-bounded
>   number is **1/4** (only 13:01->13:15, a real 14-min near-miss). Fixed:
>   `match_entries_by_strike_side_time` (20min bound, closest-in-time tiebreak, extracted
>   top-level + guard-tested: `backtest/tests/test_engine_fullhist_replay.py` 2 new tests, 7/7
>   in the module pass). Scorecard corrected in-place (append-only `_corrected_2026_07_25` block
>   in both `.json`/`.md`, original disclosure preserved per OP-22).
> - **Root cause of the entry-layer gap itself was ALREADY disclosed** (not new this fire) in
>   that same test file's docstring: live sources levels from a curated + multi-day
>   memory-merged `key-levels.json` feed; `orchestrator.run_backtest` recomputes levels from
>   bars only, a scope limitation of that specific harness. This fire's contribution is
>   quantifying it correctly (3/4 missing, not 2/4) and killing the false-positive matcher class.
> - **Does NOT itself explain the 0-for-12** (important scope discipline, OP-33): `vwap_continuation`
>   and `vix_regime_dayside` were validated by a DIFFERENT harness family entirely
>   (`backtest/autoresearch/_b5_vix_regime_dayside.py` and its vwap_continuation sibling, per
>   `analysis/recommendations/vix_regime_dayside.json#generated_by`) -- NOT
>   `orchestrator.run_backtest`, which the scope-disclosure at the top of
>   `engine_fullhist_replay.py` confirms only models the RIDE_THE_RIBBON family. This finding
>   confirms the RISK CLASS (entry-generation-vs-live parity gaps exist, and anchor-matchers can
>   hide them) but is NOT itself the smoking gun for the disarmed setups.
> - **NEXT STEP (concrete, not yet done):** audit whether `backtest/autoresearch/
>   _b5_vix_regime_dayside.py` (and the vwap_continuation autoresearch script) source their
>   entry levels/triggers the same batch-computed-only way vs live's curated+memory-merged feed
>   -- if yes, THAT is the mechanism. Needs a similar reproduce-on-a-verified-day pass, on those
>   specific scripts, not `engine_fullhist_replay.py` again.
> - Lesson filed: `_lesson-inbox/2026-07-25-anchor-matcher-strike-side-only-false-positive.md`
>   (generalizable rule: any anchor matcher joining on a coarse key needs a time-proximity bound,
>   or a coincidental collision silently reports as a false PASS).
> - Zero trading-path touched (analysis/tooling/test files only, no params/heartbeat_core/
>   filters/CLAUDE.md). Revert: `git revert <this commit>`.

> **PROGRESS 2026-07-25 ~20:30-21:05 ET (conductor, AFTERHOURS), analysis-only, no commit.**
> Picked up the prior fire's own NEXT STEP verbatim: does `_b5_vix_regime_dayside.py` (vix_regime_dayside)
> and `_edgehunt_vwap_continuation.py` (vwap_continuation) source entry levels/triggers the same
> batch-computed-only way `orchestrator.run_backtest` does (vs live's curated+memory-merged
> key-levels.json feed)? **Answer: NO -- this mechanism does NOT apply to either disarmed setup.**
> Code-read, not guessed (OP-33):
> - Both entry triggers are computed from `session_vwap_asof` (shared single implementation in
>   `autoresearch/infinite_ammo_discovery.py`, imported by both scripts verbatim) -- a pure
>   cumulative-VWAP-from-RTH-bars calculation. Grepped both files for `key.levels`/`key_levels`:
>   zero hits in either. Neither setup's trigger touches the curated/memory-merged level feed at
>   all -- unlike the RIDE_THE_RIBBON family (`engine_fullhist_replay.py`'s own scope), there is no
>   batch-vs-live level-source divergence possible here because there is no level source; VWAP and
>   VIX-regime are both derivable identically from the same OHLCV bars live and in backtest.
> - Both scripts' exit simulation is `lib.simulator_real.simulate_trade_real` (grepped: both
>   import + call it directly, not a re-derivation) -- the SAME entry+1 convention that
>   `markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md` ruled live-faithful earlier today.
>   So both the entry-generation layer AND the exit-simulation layer for these two setups already
>   use the mechanisms already confirmed correct -- **this fully closes off the
>   entry-bar-convention / batch-vs-live-level-source hypothesis for vwap_continuation and
>   vix_regime_dayside specifically** (it was never a live candidate for these two once you read
>   what their triggers actually depend on; it only ever applied to the RIDE_THE_RIBBON family).
> - **What's left as the leading hypothesis** (already named by the item's own arm-time
>   disclosure, not new): the params.json "L174 NOT INDEPENDENT / lift is largely day+side
>   selection" caveat + small OOS n (EDGE-HUNT-VERIFIED.json shows vwap_continuation's ITM2/-8%
>   cell at n=149 full / oos_n=42 -- NOT tiny, which weakens a pure-small-n explanation and
>   strengthens the "selection, not independent trials" reading: if day+side was itself chosen
>   post-hoc from the same data used to grade it, the nominal n overstates the effective
>   independent-trial count, and a 0-for-12 on an unlucky forward stretch stops looking like
>   p<1% and starts looking like ordinary post-hoc-selection decay).
> - **NOT DONE (concrete next step, if this thread is picked up again):** quantify the effective
>   independent-trial count under L174's own selection mechanism (e.g. day-cluster the historical
>   OOS trades and check how many genuinely distinct day+side buckets fed the "day+side selection"
>   vs how many the 0-for-12 forward sample drew from) -- that is the test that would either
>   confirm or refute "this was foreseeable overfitting" vs "this is genuinely a new regime".
>   Scope: research-only, no engine change implied either way.
> - Zero trading-path touched, zero files edited this fire (pure code-read + queue note).

> **PROGRESS 2026-07-25 ~21:12-21:50 ET (conductor, AFTERHOURS), commit `9ad0a907`.** Did the
> LIVE-sample half of the prior fire's NOT-DONE step (day-clustered the actual 0-for-12 rows from
> `journal/trades.csv`, not yet the historical OOS(2026) signal population -- that half is still
> open, see below).
>
> - **Finding:** the 12 CSV rows are only **4 distinct calendar days** (07-16/07-20/07-21/07-22)
>   and **4 distinct (day,side) buckets** -- same-day re-entries + same-signal TP1/runner leg
>   splits (2026-07-20 vix_regime_dayside: 4 rows, 2 sharing an IDENTICAL entry timestamp
>   09:54:19; 2026-07-21 vwap_continuation: 2 rows both at 10:11:29) collapse row-count well below
>   trial-count. AND on 2026-07-21 both `vix_regime_dayside` AND `vwap_continuation` fired PUT
>   the SAME day -- confirms in DATA the mechanism the earlier fire proved in CODE (both derive
>   `side` from the identical `session_vwap_asof` classifier): a wrong day-trend read shows up as
>   2 "setup failures", not 1.
> - **Reframe (not a reversal of the disarm, a correction of HOW SURPRISING the evidence is):**
>   "0-for-12 at 55-64% claimed WR is p<1%" -> honestly "0-for-4 correlated day-outcomes at the
>   same claimed WR is ~1.7%-4.1%" -- still worth the disarm-and-investigate call that was already
>   made, but no longer reads as a clean statistical-pipeline-falsification signal on its own.
> - **Graduated to code** (not just a one-off finding): `trade_to_learn_digest.py` now reports
>   `n_distinct_days` / `n_distinct_day_side_buckets` per setup + a `cross_setup_same_day_side`
>   field for any future setup-pair sharing a classifier -- so the next since-arm read never
>   needs a by-hand CSV pull to catch this again. 4 new guard tests + fixed 1 unrelated
>   pre-existing stale-hardcoded-list test failure (verified via git-stash: identical failure
>   with/without this commit, caused by today's earlier disarm changing params.json, not by this
>   change). Lesson filed:
>   `_lesson-inbox/2026-07-25-since-arm-fills-are-not-independent-trials.md`.
> - **STILL NOT DONE (the other half):** the HISTORICAL OOS(2026) side of the original ask --
>   day-cluster the 42-trade (vwap_continuation ITM2/-8%) / 21-trade (vix_regime_dayside) OOS
>   populations used to VALIDATE these cells, to quantify L174's "lift is largely day+side
>   selection" claim on the validation side (not the live-sample side just closed). Needs
>   `detect_signals()` re-run over the 2026 window from each autoresearch script (detection only,
>   no full sim sweep) -- tractable, not yet done.
> - Verified this fire (OP-33): all dates/times/pnl above are direct `journal/trades.csv` reads,
>   not inferred; `n_distinct_days`/`cross_setup_same_day_side` values reproduced by running
>   `trade_to_learn_digest.py --dry-run` post-commit. Zero trading-path touched (no params/
>   heartbeat_core/filters/CLAUDE.md) -- pure observability tooling + tests + docs. Revert:
>   `git revert 9ad0a907`.

> **PROGRESS 2026-08-02 (conductor, WEEKEND) -- closes the HISTORICAL OOS(2026) half (the
> "STILL NOT DONE" item named above), item now `status:CLOSED`.** Re-ran each setup's own
> byte-identical detector (`_edgehunt_vwap_continuation.detect_signals`,
> `_b5_vix_regime_dayside.detect_opt_signals` at the live-armed cell's own knobs
> low_margin=0.25/slope_rule=not_rising) over the 2026 OOS window (through 2026-07-22, the
> latest master-file coverage; detection-only, no full sim re-run).
> - **Finding: 94.1% overlap (32/34).** `vix_regime_dayside`'s 34 OOS(2026) signals are almost
>   entirely the SAME (date,side) as `vwap_continuation`'s 61 OOS(2026) signals -- exactly
>   matching a caveat already written into `analysis/recommendations/vix_regime_dayside.json`
>   ("L174 NOT INDEPENDENT of #1: 100% same-side subset of vwap_continuation") at arm-time but
>   never quantified. Pooling both setups' OOS populations by (date,side) collapses the naive
>   95-signal sum (61+34) to 63 distinct trials -- a 33.7% reduction once overlap is removed.
> - **Confirms, at the validation layer, the same mechanism the live-sample half already found**
>   (2026-07-21 firing BOTH setups on the same PUT call): a live 0-for-12 spanning two setups
>   that share a classifier is closer to a 0-for-N run on N << 12 independent day-outcomes, at
>   BOTH the live-sample layer (4 distinct day+side buckets, closed 07-25) and now the
>   OOS-validation layer (this fire).
> - **Reframes, does not reverse, the disarm.** The disarm call (07-25) stands correct on its
>   own evidence bar; this closes the open statistical-significance question honestly rather
>   than leaving "p<1% across 12 independent trials" as the operative (overstated) framing.
> - **Recommendation for any future re-arm:** score combined-setup n by pooled distinct
>   (date,side) buckets, not raw row-sum; do not count `vix_regime_dayside` as adding
>   independent coverage beyond `vwap_continuation` -- it is a VIX-favorable overlay of the
>   same edge.
> - Artifacts: `backtest/tools/zero_for_twelve_oos_day_cluster_2026_08_02.py` (detection-only,
>   $0, 1.8s) + `analysis/recommendations/zero-for-twelve-oos-day-cluster-2026-08-02.json` +
>   guard `backtest/tests/test_zero_for_twelve_oos_day_cluster.py` (3/3 green, golden-pinned).
>   Lesson filed: `_lesson-inbox/2026-08-02-oos-signal-populations-can-silently-overlap-across-setups.md`
>   (candidate graduation: a canonical `pooled_distinct_trials` helper next to
>   `probe_stats.py`, not built this fire -- flagged for skill-author).
> - Zero trading-path touched (tools/tests/analysis/queue only). Curated safety gate 59/59
>   PASS post-change. Revert: `git revert <this commit>`.

### AUDIT-BLINDSPOT-CLAUDE-NATIVE-TASKS (MED, filed 2026-07-25)

### OFF-BOX-DEADMAN-SWITCH (MED, filed 2026-07-25 -- the part the liveness fix CANNOT do)

- [ ] OFF-BOX-DEADMAN-SWITCH (MED) :: 2026-07-24 the machine was off all day, 0 engine ticks, and
  nothing reported it -- the watchdog shares a failure domain with the thing it watches. Shipped
  07-25: `engine_liveness_check.py` + a calendar-aware `session_ran` health check + an EOD-brief
  lead-line alarm. Those make the NEXT run loud; they still cannot page J WHILE the box is off.
  Only an off-box heartbeat can (cheap options: a free uptime-monitor pinging a tiny endpoint the
  rig writes to, or a phone-side cron reading the Discord bridge's last-post timestamp). Scope it
  small -- this is a monitoring nicety, not an engine feature. depends:none :: status:pending
  **AWAITING J 04:53 ET 2026-09-03 (Fable, scoped):** the only thing that can page J while the box is OFF lives off the box, which means J's account or J's phone -- OP-0 #3 (outward-facing setup on J's behalf). Two concrete $0 recipes ready to wire the moment J picks one: (a) a free uptime monitor (e.g. any free HTTP-check service) pointed at a tiny 'last-tick' page the rig already can publish -- the rig side is `engine_liveness_check.py`'s JSON plus a one-line static host (Discord webhook or GitHub Pages of a gitignored file are both $0); alert if the timestamp is > 20 min old during 09:30-16:00 ET; (b) a phone-side Shortcut/Tasker rule reading the Discord bridge's last-post time. Rig side of (a) can be built in 30 min once J names the service; nothing to do before that. :: status:awaiting-j

### CATASTROPHE-CAP-WIDEN-WATCH (MED, accrue-then-decide, filed 2026-07-23 EOD)

### ENGULFING-AT-STRUCTURE-TRIGGER (HIGH, THE build -- 3 live exhibits, mirror-symmetric, untested by the 181-cell matrix)

### DOUBLE-BOTTOM-DISARM-DECISION (HIGH, 24h re-audit then act, filed 2026-07-23 overnight kitchen)

### TRENDLINE-TIGHT-EXIT-ACCRETE (MED, watch candidate from the kitchen's best near-miss)

### RIBBON-SESSION-SCOPE-DIVERGENCE (HIGH, discovery from the TV parity oracle 2026-07-23)

### EDGE-MATRIX-NIGHTLY-RERUN (MED, standing loop wiring)

- [ ] EDGE-MATRIX-NIGHTLY-RERUN (MED) :: Wire backtest/tools/edge_matrix_rerun.py into the
  conductor AFTERHOURS rotation (weekly full re-run as OPRA days accrue; the "infinite
  backtesting" standing loop J asked for). Family runners need the incremental --since flags
  finished (TODOs in the stub). New days shift the held-out window forward per the frozen
  protocol -- never re-tune on formerly-held-out days without disclosing.
  depends:none :: status:in_progress-step1-of-4-done

  > **[2026-07-23 ~06:12-06:55 ET conductor] Step 1 (day-inventory forward-extend) SHIPPED
  > this fire** -- was a bare stub referencing a script (`build_day_inventory.py`) that had
  > never actually been built (verified: `Glob "**/build_day_inventory*"` -> zero hits before
  > this fire). Built `backtest/tools/build_day_inventory.py` (`--extend`/`--status`):
  > forward-extends the FROZEN `day-inventory-2026-07-23.json` with any new trading days
  > accrued in the SPY/VIX 5m caches since its last day (2026-07-22), computing has_opra/
  > n_opra_files/gap_pct/n_rth_bars/partial mechanically and day_type/vix_band via the SAME
  > formulas recorded in the original's own `method` field (verified via grep across all 6
  > `edge_matrix_*.py` family runners that day_type/vix_band are DISCLOSURE-ONLY, never a
  > gate/filter -- safe to best-effort-classify forward days). `heldout_days` is carried
  > through VERBATIM, never touched (rerun protocol rule 2). Writes a NEW file,
  > `analysis/edge-matrix/day-inventory-extended.json` -- deliberately NOT the stub's proposed
  > `-<today>.json` naming, which would collide with the frozen original's own filename the
  > very first time this runs (today literally IS 2026-07-23, and that suffix encodes the
  > EDGE MATRIX build, not a run date); corrected `edge_matrix_rerun.py`'s own docstring to
  > match. The 6 family runners' hardcoded `INVENTORY_PATH` constants are UNCHANGED -- this
  > step only makes forward days computable/inspectable, it does not yet feed them anywhere
  > (that's Step 2, per-runner `--days-after` flags, still a TODO).
  >
  > **Verified this fire (OP-33):** ran `--status`/`--extend` live against the real repo state
  > -> 0 pending days (correct: it's 06:xx ET 2026-07-23, today's session hasn't traded yet,
  > so there is genuinely nothing to accrue) -- confirmed the output is a byte-for-byte content
  > match of `days`/`opra_days`/`heldout_days`/`excluded_fragments` against the frozen original
  > when 0 new days exist (`python -c` diff, all `True`). Since the real "adds a day" path
  > can't be exercised against live data yet, built 17 guard tests
  > (`backtest/tests/test_build_day_inventory.py`) with synthetic fixture SPY/VIX/OPRA files
  > covering: zero-pending no-op, a genuine new day added with correct has_opra/n_opra_files/
  > n_rth_bars/gap_pct, a <30-bar fragment correctly excluded (not added to `days[]`), a
  > 30-70-bar day correctly flagged `partial`, `heldout_days` provably NOT gaining the new day,
  > plus direct unit coverage of the 3 pure classification helpers (`_vix_band`,
  > `_classify_day_type`, `_atr20`). **RED-proofed live:** injected a deliberate gap_pct
  > formula bug (`*200` instead of `*100`) -> `test_extend_adds_one_new_day_with_correct_fields`
  > failed with the exact expected mismatch (`2.0 != 1.0`); reverted -> 17/17 green again. Full
  > `pytest backtest/tests/test_build_day_inventory.py backtest/tests/test_task_scorer*.py -q`
  > -> 79/79 PASS, no regression.
  >
  > **Scope + revert:** pure research-tooling build (1 new script, 1 new test file, 1 docstring
  > correction in `edge_matrix_rerun.py`, 1 generated JSON artifact) -- zero params/
  > heartbeat_core/filters/placement/exit/CLAUDE.md touched, no live wiring, no broker import.
  > Ships per OP-22 (engine-benefit research infra). Revert: one commit.
  > **Remaining (named, NOT done this fire -- rail 3, one bounded task):** Step 2 (per-family
  > `--days-after` incremental flags on the 6 `edge_matrix_*.py` runners -- genuinely
  > "hours-of-grind, weekend-grade" per the stub's own warning, not a single-fire slice), Step 3
  > (matrix-wide BH recompute + `EDGE-MATRIX-2026-07-23.md` rerun-delta doc section), Step 4
  > (watermark file + conductor AFTERHOURS rotation wiring). Next natural trigger for
  > re-verifying the new-day-add path against REAL (not synthetic) data: any future fire after
  > today's session closes and the SPY/VIX 5m caches gain a 2026-07-23 file.

### MIN-TRIGGERS-BULL-ASYMMETRY-AB (MED, pre-reg follow-up, filed 2026-07-23 from the mirror-parity audit)

### CHEF-FOCUS-FILTER (HIGH, after-hours build, filed 2026-07-22 night -- enforces FOCUS-DOCTRINE)

### CHEF-CANDIDATES-CONSOLIDATION-SWEEP (HIGH, follow-up split off CHEF-FOCUS-FILTER part 4, filed 2026-07-22 night)

### GAMMA-STUDY-CURRICULUM (MED, standing conductor mode, filed 2026-07-22 night, J-directed "learn new things -- TA, indicators, risk management... like a person")

### PULLBACK-HOLD-BULL-TRIGGER (HIGH, THE bull-side build, filed 2026-07-22 Fable review -- supersedes the framing of MORNING-BULL-QUALITY-GATE-RECONSIDER)

- [ ] PULLBACK-HOLD-BULL-TRIGGER (HIGH, Lane-A vocabulary build + Lane-B pre-reg validation) ::
  ROOT CAUSE, three exhibits in two days: the engine's ONLY high-conviction bull trigger
  (ELITE level_reclaim) is structurally LATE -- a reclaim by definition fires AFTER the move.
  Late bull entries bled historically (bull n=80 WR 1.2%) so block_elite_bull was added; the
  net system now fires bull at TOPS and then blocks itself = zero core bull participation on
  up days. The block is a tourniquet on a late trigger, not the disease.
  EXHIBITS (all verified from core-decisions.jsonl):
    * 07-21 10:40-11:15: three taps of a shelf, engulfing, bull 9-10 -- triggers=[] -- SPY ran
      746.77->748.97 uncaptured. Trigger finally fired 12:21 at 748.47 (the top), blocked;
      J ruled the 12:21 class "needs to not happen".
    * 07-22 10:45-10:50 (J live, angry): pullback low 746.80 sat 26c above a KNOWN
      level_memory level at 746.54 (the engine SAW the level, levels_context quoted) --
      triggers=[] -- ribbon still labeled BEAR (flipped BULL 11:16, 30 min LATE, C28 on the
      entry side) -- extra lanes already dead (3 vwap stops -$108 then RISK_DENY_SETTLEMENT/
      vetoes/SKIP_LATE_ENTRY). SPY ran 746.80->749.98 (+$3.2) uncaptured. Trigger finally
      fired 11:31 bull=11 at 749.41 (+$2.6 above J's entry) -- blocked, and TODAY the block
      was locally CORRECT (price went sideways then faded): the trigger fired at the top again.
  THE BUILD (vocabulary, Lane A): a PULLBACK-HOLD bull trigger -- in an emerging/confirmed up
  structure, price pulls back and HOLDS above a known level (zone band per levels-are-zones,
  never penny-exact; e.g. low within band of level, N bars hold, close back above minor
  structure) -> bull entry NEAR support, stop below the zone. Enters $2-3 EARLIER than
  level_reclaim ever can. This is J's actual repeated pattern (07-21 shelf + engulfing,
  07-22 higher-low at 746.54-746.80).
  VALIDATION (Lane B, before any live wire): frozen pre-reg -> detector over history ->
  real-fills replay through exit_manager_walk -> full 4-condition gate + concentration +
  BH-FDR. The RSI-reset observation (J 07-21) and ribbon-spread observation (retraction doc)
  are candidate CONFIRMATION features inside this trigger, not separate gates.
  REFRAMES MORNING-BULL-QUALITY-GATE-RECONSIDER: the answer to "unblock elite bull?" is NO --
  unblocking admits late tops (07-22 proved the block right at 11:31). The fix is the EARLY
  trigger, not removing the guard on the late one. Conductor: stop surfacing the reconsider
  item as J-gated; point it here. depends:none :: status:CLOSED-LANE-B-NO-CELL-SHIPS
  (2026-07-22 ~18:42 ET -- Lane-A stays shipped shadow-only; Lane-B closed honest-null, see
  closing block below the Lane-A build for full verdict)

  **LANE-A BUILT 2026-07-22 ~18:12-19:10 ET (conductor, AFTERHOURS).** Built exactly the
  vocabulary the item specifies: `detect_pullback_hold_bullish` in `backtest/lib/filters.py`
  -- scans an approach window for the EARLIEST bar achieving the lowest low inside a level's
  zone band (`PULLBACK_HOLD_ZONE_BAND_DOLLARS=0.30`, same width as the already-doctrine
  `CONFLUENCE_TOLERANCE_DOLLARS`, not hand-picked), requires >= `PULLBACK_HOLD_MIN_HOLD_BARS=2`
  bars where the CLOSE never breaks the zone floor, then fires when the current bar closes
  above the highest close of that hold window. SHADOW-LOGGED ONLY (`BullishSetupResult
  .shadow_triggers_fired`, same precedent as `wick_reclaim`/`trendline_reclaim`) -- NOT wired
  into `triggers`/`bull_score`/`passed`; cannot affect live scoring until Lane-B clears.
  **Verified against the item's OWN 07-22 exhibit** (real SIP 5m bars from
  `backtest/data/spy_5m_2026-05-19_2026-07-22.csv`, not a synthetic-only claim): fires at the
  10:50 ET bar (2 bars after the 10:40 pullback low of 746.78, 22c inside the zone band around
  level 746.54), i.e. BARS EARLIER than `level_reclaim` (which per the exhibit doesn't confirm
  until ~748+, the session top) -- the exact "$2-3 earlier" the item claims, now demonstrated
  on real tape rather than asserted. Guards: `backtest/tests/test_pullback_hold_trigger.py`
  (11/11 -- real-tape fires-at-10:50 + does-not-fire-at-the-low-bar-itself +
  insufficient-hold negatives + 6 synthetic edge cases covering every branch) +
  `backtest/tests/test_pullback_hold_shadow_only.py` (2/2 -- zero-behavior-change proof using
  a byte-identical current bar between the fires/doesn't-fire variants so
  level_reclaim/wick_reclaim/trendline_reclaim are proven unaffected by construction, not by
  coincidence; RED-proofed live during authorship by temporarily leaking `pullback_hold` into
  `triggers` -- caught the contamination, reverted, confirmed green again, exactly the
  `test_bull_trendline_wick_reclaim_shadow_only.py` precedent's own methodology). Zero
  regressions: `test_wick_reclaim_trigger.py` + `test_trendline_reclaim_trigger.py` +
  `test_bull_trendline_wick_reclaim_shadow_only.py` + `test_bull_sequence_reclaim_coupling.py`
  all still 15/15; gym 104/104 GREEN (`crypto/validators/runner.py`).
  **LANE-B NOT RUN THIS FIRE (scope discipline, rail 3 one-bounded-task-per-fire):** the
  item's own text separates "vocabulary build" (Lane A, done) from "frozen pre-reg -> detector
  over history -> real-fills replay through exit_manager_walk -> full 4-condition gate +
  concentration + BH-FDR" (Lane B) -- that is a SEPARATE, larger fire (needs a frozen grid on
  `min_hold_bars`/`zone_band_dollars` before running, an OPRA-cache real-fills pass, and
  BH-FDR across the grid, matching the exact discipline `rsi_extension_block_probe.py`
  already used). Next bounded step for the next fire: pre-register that grid (do NOT
  hand-tune off the one 07-22 exhibit -- C25/no-post-hoc-picking) and run it.
  **Rail-4 scope: SHADOW-ONLY, not a trading-path change.** `evaluate_bullish_setup`'s
  `passed`/`bull_score`/`triggers_fired`/routing are provably untouched (see the shadow-only
  guard above) -- this ships as engine-benefit observer/authoring work, same class as the
  wick_reclaim/trendline_reclaim precedent, not a params/heartbeat_core/filters-live-path
  change requiring guard+revert+REVOKE under rail 4.

  **LANE-B RUN 2026-07-22 ~18:19-18:42 ET (conductor, AFTERHOURS) -- VERDICT: NO_CELL_SHIPS
  (honest null). CLOSED.** Frozen pre-reg
  (`analysis/recommendations/pullback-hold-bull-prereg-2026-07-22.json`, 36-cell grid --
  `up_structure_mode{MARKET_STRUCTURE,PRICE_VWAP} x zone_band_cents{15,25,40} x
  hold_bars_n{1,2,3} x confirm_mode{NONE,BOTH}`) -> `detect_pullback_hold_bull`
  (`backtest/tools/pullback_hold_bull_detector.py`) -> full-history detector-frequency pass
  (44 days) + real-fills dollar pass via `exit_manager_walk`/`option_pricing_real` on the
  39-day OPRA-covered subset (`backtest/tools/pullback_hold_bull_replay.py`) -> ship-bar
  conditions 1-5 + BH-FDR q=0.10, evaluated against the 10-day held-out tail
  (2026-07-01..07-17) and BOTH of J's own named live exhibits as sanity anchors (fidelity
  gate, evaluated BEFORE dollar economics per the pre-reg's own `cell_disqualified_if`).
  **RESULT: 0/36 cells clear both sanity anchors -- anchor_1 (2026-07-22 10:44-10:53 ET,
  the pullback low at 746.80 over LevelMemory's independently-found 746.54 level) is missed
  by EVERY cell**, because both up-structure qualifier candidates read False AT the
  pullback-low bar itself (PRICE_VWAP recovers True 15 min late, MARKET_STRUCTURE 45 min
  late) -- the confirmation layer built to fix the "trigger fires too late" problem is
  ITSELF too late to see J's own earliest read. Anchor_2 (07-21 shelf) fires on 18/36 cells,
  but the AND-gate on both anchors still disqualifies the whole grid. Even ignoring the
  fidelity gate: 0/36 clear condition_2 (day-majority win) or condition_3 (survives dropping
  the single best trade) -- the only cell with positive aggregate P&L
  (`PRICE_VWAP_band40c_N1_NONE`, 506 signals/39 days = ~13/day) nets `total-top_trade =
  -$56.21`, i.e. one outlier trade explains the entire "profit" (C24 anchor-trade
  anti-pattern) and it's a high-frequency/low-selectivity fire (C27). 0/36 cells clear
  BH-FDR at q=0.10 (best p-value 0.44). Tighter bands (15c/25c) get WORSE, not better, as
  hold-bars N grows.
  **Verified this fire (OP-33):** `pytest backtest/tests/test_pullback_hold_bull.py -q` ->
  16/16 PASS. Independently RE-RAN the full grid (`python -m
  backtest.tools.pullback_hold_bull_replay`, background, ~15min real-fills pricing over
  36 cells x 39 days) -> reproduced `NO_CELL_SHIPS`, `shippable=0/36`, and byte-identical
  top-5 dollar figures to the pre-existing artifact -- deterministic, not a fluke read.
  Manually recomputed condition-pass counts across all 36 cells from raw `all_cells` JSON
  (not trusted the summary `verdict` string): 0/36 anchors, 1/36 cond1, 0/36 cond2, 0/36
  cond3, 15/36 cond4, 6/36 cond5 -- matches the claimed honest-null exactly. Full writeup:
  `analysis/recommendations/pullback-hold-bull-stage-summary-2026-07-22.md`.
  **Disposition:** Lane-A stays shipped (shadow-only, zero live effect, useful ingredient
  for a future differently-confirmed attempt). Lane-B is CLOSED -- no live wiring, honest
  null reported, NOT hand-loosened post-hoc to manufacture a pass (no_post_hoc_tuning
  clause honored). `MORNING-BULL-QUALITY-GATE-RECONSIDER`'s original "unblock elite bull?"
  stays answered NO. Real next step if pursued (would need its OWN fresh dated pre-reg, not
  an edit to this one): a genuinely earlier up-structure confirmation primitive than
  session-VWAP-crossing or 60-bar market-structure trend -- both pre-registered candidates
  are themselves lagging-confirmation signals, which is WHY they can't see J's earliest read.
  Rail-4 unaffected (research tool + JSON/MD outputs only, no params/orders/filters/
  heartbeat_core/strategies.py/CLAUDE.md touched, no broker import). depends:none ::
  status:CLOSED-NO-SHIP
  **LANE A SHADOW RUNNING + LANE B PREREG FILED 05:24 ET 2026-09-03 (Sonnet, Fable-verified 14 + 14 passed):** `backtest/lib/pullback_hold_detector.py` (zero engine wiring): pullback into a level zone (band $0.30 or the level's own zone_width), every LOW inside the band for K=3 bars, then a close above the zone ceiling AND above the hold window's highest close, with the 15-min HTF stack != BEAR (read-only reuse). `setup/scripts/pullback_hold_shadow.py` scores fires nightly with the sole-blocker forward-outcome proxy -> `analysis/recommendations/pullback-hold-shadow-{ledger.jsonl,summary.json}`; `Gamma_PullbackHoldShadow` 16:50 ET weekdays PT15M/PT30M, State=Ready, registry 160 -> 161. Prereg `prereg-pullback-hold-bull-trigger-2026-09-03.md`: forward window from today, bar >= 30 sessions AND >= 25 scored fires, decision = session-clustered CI-lower of the favourable rate > 0.4545 (the engine's own bull baseline, n=44); no wiring before 10-30. **Honest in-sample read (disclosed, not verdict-eligible):** on 49 sessions rebuilt from the engine's own tick log, 52 fires (~1/day), favourable 18.75% (9 / 13 / 26 flat) -- well BELOW the baseline; and `levels_active` was empty in the decision rows before 07-28, so neither 07-21/07-22 exhibit fires under the production field (07-21 fires only under the exploratory `levels_context`, at 10:35 ET; 07-22's hold was one bar short of K=3). The forward clock decides; the prior is negative. :: status:shadow-running

### SELFCHECK-TRENDLINE-DRAW-DUPLICATE-SPAM (LOW, OP-22 hygiene, filed 2026-07-22 conductor AFTERHOURS, SHIPPED 2026-09-01 conductor AFTERHOURS)

### QUEUE-MD-RETENTION-CAP (LOW, OP-22 hygiene, filed 2026-07-22 conductor AFTERHOURS)

- [ ] QUEUE-MD-RETENTION-CAP (LOW) :: `automation/overnight/queue.md` is 3322 lines / ~577KB --
  now exceeds the Read tool's 256KB single-shot limit (must offset-read in chunks). Byte
  breakdown this fire (`wc`/python len check): Active backlog 267KB (grew from 222KB two days
  ago -- the actively-growing part), `## Archived 2026-06-19` 6KB (already a rolled-up summary,
  leave alone), `## Completed` 96KB, rest (HARVESTED-FROM-GYM + all dated post-Completed
  sections) ~208KB -- mostly recent (last ~2 weeks), NOT an archive candidate without individual
  triage. :: depends:none :: status:pending

  > **[2026-07-23 ~05:45-06:10 ET conductor, AFTERHOURS] Step 1 of the named plan SHIPPED
  > this fire.** Archived the 2026-06-19..07-01 dated half of `## Completed` (119 lines /
  > 53,831 bytes, lines 2129-2247, identified via a python per-section byte-boundary scan, not
  > guessed) to `automation/overnight/queue-archive-2026-07-23-completed.md`, same precedent as
  > `queue-archive-2026-06-19.md`/`queue-archive-2026-06-20.md`. **Verified byte-for-byte
  > preserved this fire (OP-33):** diffed the archived file's body against the pre-edit
  > `git show HEAD:...queue.md` line range -- identical after normalizing an incidental
  > LF->CRLF conversion my own Python `open(...,'w')` introduced on Windows (caught by `file`
  > reporting "with CRLF line terminators" on a repo file that was LF-only; re-wrote both the
  > archive and queue.md with `newline='\n'` to restore LF-only, then re-diffed clean). Left a
  > 4-line pointer in queue.md's `## Completed` section (matches the existing
  > `queue-archive-2026-06-19.md` pointer style already there) -- confirmed via
  > `git diff --stat` the net queue.md change is a clean **4 insertions / 118 deletions**,
  > nothing else touched. Checked first that no live `Active backlog` item's `depends:`
  > references any of the 6 entry-ids in the archived range -- zero hits, safe to move.
  > `queue.md`: 577,392 -> ~537,771 bytes (still over the 256KB single-read limit -- this was
  > always going to be a multi-fire job per the item's own prior note, not a regression).
  > **Foot-gun found + fixed same fire (not filed to lesson-inbox, folded straight in since
  > it's this item's own mechanism):** a plain Python `open(path, 'w', encoding='utf-8')` on
  > this Windows box silently converts `\n` -> `\r\n` on write, which would have introduced a
  > mixed-line-ending diff across a "byte-for-byte preserved" archival claim -- any future
  > script-based file move/archive in this repo MUST open with `newline='\n'` (or read/write
  > in binary) to actually be byte-for-byte, matching this repo's LF convention. **Scope +
  > revert:** pure doc/archival move (2 files: queue.md trimmed, new archive file added), zero
  > params/heartbeat_core/filters/placement/exit/CLAUDE.md touched -- ships per OP-22 (engine-
  > benefit hygiene, same class as the chef-candidates sweeps). Revert: `git revert <this
  > commit>` (restores the 119 lines to queue.md, removes the archive file). **Remaining work,
  > not attempted this fire (rail 3, one bounded task):** still >256KB -- next bounded step is
  > triaging `## Active backlog`'s 267KB (the actively-growing section, likely has its own
  > closed-but-not-yet-marked-`[x]` or duplicate-topic entries worth a targeted sweep) and/or
  > the ~208KB of dated post-Completed sections oldest-first for genuinely-stale (not just old)
  > content. :: status:in_progress-step1-of-N-done

  > **[2026-08-09 ~01:xx ET conductor, AFTERHOURS] Step 2 SHIPPED this fire.** The file had
  > regrown to 745,505 bytes / 4153 lines (confirmed the Read tool now hard-fails on it:
  > "File content (728KB) exceeds maximum allowed size (256KB)" -- STAGE 1's own "Read
  > queue.md" instruction has been silently broken for every conductor fire since it crossed
  > that line). Individually verified-then-archived 14 whole `## `-level sections that sit
  > BELOW `## Active backlog` (the "dated post-Completed sections" half of the prior fire's
  > own remaining-work note) to `queue-archive-2026-08.md`: the old `Archived 2026-06-19` +
  > `Completed` sections (pure relocation, already-archived), plus 12 dated 2026-07-07..07-20
  > sections each confirmed fully resolved before moving (every checklist item `[x]`, or an
  > explicit CLOSED/DONE/SHIPPED/NO-SHIP marker read in full) -- AUDIT-2026-07-07,
  > 2026-07-09-profit-lock, 2026-07-11-audit-harness, 2026-07-11-profitability-plan,
  > J-INTENT-EXECUTOR, WF-GATE-STRUCTURALLY-NULL, WF-GATE-REDESIGN-METHODOLOGY,
  > TRENDLINE-FIXES-2026-07-17, WEEKEND-METHODOLOGY-REVIEW, LEVER-1-TREND-ALIGNMENT-
  > VERDICT-STANDING, SELF-CHECK-BROKEN-2026-07-20, STATE-FILE-REVERSION-2026-07-20. One
  > still-open item found buried inside the last of those (Bold's 4x-margin origin, never
  > confirmed by J) was extracted BEFORE archiving and re-filed as its own bullet in
  > `## Needs J's own hands` so it stays visible. Sections with ANY remaining open `[ ]` item
  > (HARVESTED-FROM-GYM, Twin escalations, 2026-07-09 G11 review, 2026-07-14 trendline/EDGE
  > follow-ups, EOD-2026-07-15 FIXES, VETO-HTF-CONFLICT-REGRADE, the live FABLE-ESCALATION,
  > HTF-LEVEL-LOOKBACK-EXTENSION, BOLD-TIER-BOUNDARY-HYSTERESIS-SPEC,
  > BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL, J-ONLY-COMPANION-PUSH-ACTIVATION) were left
  > untouched -- verified by machine count (`- [ ]` / `- [x]` occurrence audit per section)
  > before moving anything, not by re-reading titles. **Caught + fixed this fire's own version
  > of the EXACT CRLF foot-gun this item's step-1 note already named:** my first
  > `open(path, "w", encoding="utf-8")` (no `newline=`) silently wrote CRLF into both files
  > (`file` confirmed "with CRLF line terminators", 3137 instances) -- re-read with
  > `newline=None` (universal-newline decode) + rewrote with `newline="\n"` on both files,
  > re-verified LF-only via `file`. **Result:** `queue.md` 745,505 -> 553,913 bytes (still
  > >256KB -- the `## Active backlog` section itself, ~2478 lines / ~444KB, is the true
  > remaining bulk and was DELIBERATELY NOT touched this fire: its 138 checklist items mix
  > freely with 57 `### `-level items of near-uniform format, and an automated
  > status-marker classifier tested on all 57 came back 54/57 UNKNOWN (many are Tier-N
  > organizational headers, not real items, e.g. `### Tier 0/1/2/3/4`) -- splitting it
  > correctly needs per-item human-grade judgment, not a fresh fire's regex, so rail 3 says
  > defer rather than guess. Verified no regression: `task_scorer.py --top` ranks correctly
  > post-edit (see this fire's own STATUS.md entry); line-accounting cross-check confirmed
  > zero content lost (33 preamble + 1019 archived + 3101 kept = 4153 original). **Next
  > bounded step (step 3, for a future fire):** a purpose-built parser (reuse
  > `task_scorer._item_blocks`/`ITEM_RE` rather than reinventing) that walks `## Active
  > backlog` block-by-block and, for EACH of the 57 `### ` items individually, reads its own
  > closure state (not a keyword heuristic) before archiving -- the 138 checklist items are
  > lower-risk (already have an explicit `[x]`/`[ ]` marker) and could go first.**
  > :: status:in_progress-step2-of-N-done

  > **[2026-08-29 ~01:xx ET conductor, AFTERHOURS] Step 3 SHIPPED this fire.** Did exactly
  > the named step-3 plan for the checklist-item half (the "138 checklist items, lower-risk"
  > slice): wrote a boundary-aware parser (top-level `- [ ]`/`- [x]` bullet starts, `#`-heading
  > lines, AND `> **Archive note` lines all treated as hard block boundaries -- the naive
  > next-bullet-only boundary from the first draft of this script would have swallowed the
  > `## Active backlog` heading and the 2026-08-09/08-19 archive notes themselves into an
  > unrelated item's archived block; caught and fixed before writing anything, via a dry-run
  > that printed each block's first/last line for eyeball review). Selection: top-level bullet
  > has an explicit `[x]` checkbox OR its own `status:` tag reads done/DONE/CLOSED/
  > CLOSED_ALREADY_ANSWERED -- 29 items matched (`TP1-R50-READJUDICATION` through
  > `RIBBON-LAG-PRICE-STRUCTURE-TRIGGER`), each spot-checked by reading its actual closing text
  > (not trusting the checkbox alone -- e.g. `ENGULFING-AT-STRUCTURE-TRIGGER`'s 159-line block
  > has stray mid-block `status:pending` tags from its own superseded field/progress-note
  > history, but its top line explicitly reads "CLOSED 2026-07-25" with a full writeup + green
  > guards at the tail, confirmed genuinely closed). Also removed 16 duplicate `gamma_manager`
  > ESCALATION auto-harvest lines from the file's tail per this file's own header rule (line 4:
  > harvest noise doesn't belong here unless it names a concrete fix) -- extracted the one real
  > finding buried in them (T-OPEN-TICK-STALE-QUOTE-2026-08-20, tick freshness) and re-filed it
  > as its own visible item (`TICK-FRESHNESS-VALIDATION-2026-08-20`) rather than losing it.
  > **Verified, quoted (OP-33):** a formal byte-exact round-trip check (not eyeballing) --
  > reconstructed the archive file's body from the exact same block-boundary computation applied
  > to a fresh git-HEAD read and confirmed it matches the actual written archive file
  > character-for-character (`removed_str == reconstructed archive content: True`); confirmed
  > zero live item's `depends:` references any archived id (grepped before moving); confirmed
  > the file's own drift-in-flight (a same-session `TWIN-ESCALATION-20260829-...` line appended
  > by a concurrent process between HEAD and my read, L214/C34 shared-checkout caution) survived
  > untouched in the edited file. `pytest backtest/tests/test_queue_md_retention_cap.py -q` ->
  > `3 passed`; `run_safety_gate.py` (6 curated suites) -> `59 passed, PASS`;
  > `task_scorer.py --all` re-parses cleanly post-edit. **Result:** `queue.md` 443,702 ->
  > 339,186 bytes (still >256KB single-read limit but now well under the 450,000-byte guard
  > threshold, and a genuine step toward it -- the remaining bulk is the `### `-level dated
  > sections the step-2 note explicitly deferred, still needing real per-item judgment, not a
  > regex). New archive: `queue-archive-2026-08-29.md` (107,348 bytes, 29 items + noise
  > cluster). **Scope + revert:** pure doc/archival move, zero params/heartbeat_core/filters/
  > CLAUDE.md touched -- ships per OP-22 (engine-benefit hygiene). Revert: `git revert <this
  > commit>` (2 files: queue.md restored, archive file removed). **Remaining work (step 4, next
  > fire):** the `### `-level dated sections below `## Active backlog` (the 57-item population
  > the step-2 note's automated classifier came back 54/57 UNKNOWN on) -- needs a per-section
  > read, same discipline as this fire, not a keyword heuristic.
  > :: status:in_progress-step3-of-N-done

  > **[2026-09-03 conductor, AFTERHOURS] Step 4 shipped a $0 deterministic REPLACEMENT for this item's hand-consolidation loop.** `setup/scripts/queue_consolidate.py` (stdlib-only, no LLM) parses `## Active backlog` onward into top-level blocks, selects only a block whose checkbox is `[x]` AND (its LAST `status:` field resolves to done/closed/resolved/cancelled/canceled/decided/shipped, OR its head line names an exact-case CLOSED/DONE/SHIPPED/RESOLVED marker alongside a date), holds back any candidate a still-open item's `depends:` still references (prints the reason, does not archive it), writes selected blocks verbatim (LF-normalised) to `queue-archive-<date>.md` (new `## Tranche N` section if today's file already exists, matching `queue-archive-2026-09-02.md`'s shape), and inserts/updates ONE pointer line directly under the heading -- reads and writes BYTES throughout, never a text-mode `open(path, 'w')`, so the LF->CRLF foot-gun this item's own step-1 note (2026-07-23) found can't recur a second time. 17/17 new guard tests (`backtest/tests/test_queue_consolidate_2026_09_03.py`, tmp_path fixtures only, never the live file), RED-proofed with 3 independent hand-mutations (terminal-status set, depends-block, CRLF-preservation -- each correctly failed the suite pre-revert). Live dry-run this fire found queue.md at 451,186 bytes (over the 450,000 cap) but 0 currently-archivable candidates -- already hand-consolidated ~40min prior this same session, nothing newly closed since; caught and fixed one real false positive in the process (PHONE-HALT-COMMAND's own "fail-closed guard" prose case-insensitively matched the CLOSED marker before the fix -- now exact-case only). `--apply` was never run against the live file this fire, dry-run only per task scope. Default is `--dry-run`; `--apply` writes; `--min-headroom` (default 20000 bytes) prints a LOUD line post-apply if still close to cap rather than reaching for open items to force it down. Next fire that trips this guard: run `python setup/scripts/queue_consolidate.py --apply` FIRST, before any hand pass. :: status:tooling-shipped-dry-run-only

### DOUBLE-BOTTOM-LOOKBACK-AB (MED, pre-reg proposal, filed 2026-07-21 dojo overnight)

### DB-BASE-QUIET-PROXIMITY-GATE-LEAD (MED, investigate, filed 2026-07-21)

- [ ] DB-BASE-QUIET-PROXIMITY-GATE-LEAD (MED) :: NEW LEAD from the diagnosis above: the detector
  fires ~22x/35 days under near-real conditions with levels_active=[], yet production shows
  "0 fills since arm" over 20+ days (STATUS.md LICENSE-MONITOR). The gap points at the
  NOT_NEAR_NAMED $0.50 proximity gate (Gate 6) as the dominant production suppressor -- NOT
  reproduced in the diagnostic (needs the full level-detection pipeline). Measure how many of
  those 22 fires die on proximity, and whether $0.50 is the right band given the levels-are-zones
  doctrine (J 2026-07-17). depends:none :: status:pending

### RSI-EXTENSION-BLOCK-ELITE-BULL (HIGH, Lane-B pre-reg, filed 2026-07-21 dojo session, J RULING)

> **PRE-REG RAN 2026-07-22 ~16:xx ET (conductor, AFTERHOURS).** Built
> `backtest/autoresearch/rsi_extension_block_probe.py` exactly as pre-registered above (grid
> X in {65,68,70}, Y in {50,55}, N in {6,10} bars, Z in {3,4,5}$, frozen before running, BH-FDR
> q=0.10 across all 15 grid cells). Re-ran the SAME real-fills A/B methodology as the CLOSED
> bull-unblock SLICE 1 (`block_elite_bull` True vs False) but widened the window to the latest
> OPRA-cached trading day (2026-05-21..2026-07-17, vs SLICE 1's 05-21..06-30) to get more than
> n=7 to test the discriminator against. **Result: removed-by-block_elite_bull cohort n=9
> (only 2 more trades than SLICE 1 found on the narrower window) -> VERDICT
> INCONCLUSIVE_SAMPLE_TOO_SMALL** (n<10, same statistical-power ceiling as every prior
> bull-frontier probe). **More important honest finding than the n-shortfall itself: at the
> MOST PERMISSIVE grid point (X=65), only 1 of the 9 real trades even qualifies as
> "RSI-extended" â€” 8/9 sit at RSI 47-62 at entry, not clearly "extended" by RSI(14) on 5m bars.**
> So the discriminator J read correctly off the ONE 2026-07-21 exhibit (RSI 68.8 vs 63.6, extension
> vs reset) does not describe the wider removed-cohort population as measured â€” it may still be
> real for THAT specific pair, but it is not (yet) a general rule this data can confirm. J's own
> 11:15/12:21 exhibits themselves fall OUTSIDE this probe's option-cache window (cached only
> through 2026-07-17) so they could not be individually priced here â€” reported as a gap, not
> papered over. **Verdict is a genuine null, not a rejection of the idea:** the honest next step
> is the SAME one every other bull-frontier thread landed on (CLIMB-LADDER-NEXT-RUNG-IS-CLASS,
> BULL-UNBLOCK-REPLAY-PROBE) â€” widen the window as more OPRA cache accrues, then re-run this
> EXACT frozen grid (no re-picking) rather than hand-tuning post-hoc. Guard:
> `backtest/tests/test_rsi_extension_block_probe.py` (9/9, pins the INCONCLUSIVE verdict + the
> "only 1/9 qualifies" population-thinness finding + non-vacuous unit checks on the pure
> condition functions + BH-FDR helper). Zero regressions: 27/27 across this + the 3 sibling
> bull-unblock probe test files. Result: `analysis/recommendations/rsi-extension-block-elite-bull-2026-07-22.json`.
> Rail-4 CLEAR: pure research probe + JSON + guard test â€” touches NO params/filters/heartbeat/
> CLAUDE; no live wiring proposed (there is nothing to propose â€” the grid didn't clear).

### EOD-DOJO-EXHIBIT-MANIFEST (HIGH, after-hours build, filed 2026-07-21 ~14:45 ET, J-directed)

### DOJO-EXIT-HARNESS-BUGS (HIGH, after-hours fix, filed 2026-07-21 ~08:xx ET -- verdict VOID until fixed)

### DOJO-FLEET-HISTORICAL-SIGNAL (HIGH, Phase 1b, filed 2026-07-20 ~23:40 ET) :: The dojo's 3 fleet
  arms (safe-3/risky-1/risky-3 = the RIBBON/control/ZONE-RIDE exit-diversity lanes, the WHOLE
  point of J's "watch each arm trade the same signal differently" vision) currently render
  FLEET_VIEW_PENDING in the whisper because setup/scripts/dojo/engine_step.py can only produce
  the 2 core arms (safe/bold). Root cause: build_shared_signal.py builds its signal from TODAY's
  on-disk core-decisions.jsonl/sight-beacon.json, not a date-parameterized historical bar. FIX:
  make the shared-signal builder replay-aware (accept a replay_day + the sliced bars), then have
  engine_step run fleet_executor.plan_all on that historical signal per arm so the whisper shows
  all 5 arms' gated+sized+exit-profiled views. CAREFUL: build_shared_signal.py is a shared
  PRODUCTION module -- blast-radius grep + guard that the live path is byte-unchanged (add a
  replay-only code path, do not mutate the today path). This is what turns the dojo from a 2-arm
  demo into J's full exit-diversity experiment. depends:none :: status:done (committed 24bc365 2026-07-21; live build() byte-unchanged 58/58; dojo renders 5 arms differentiated)

### DOJO-HISTORICAL-KEY-LEVELS-SNAPSHOT (MED, Phase 1b, filed 2026-07-20 ~23:40 ET) :: engine_step
  parity on 2026-07-17 is ~87% verdict/side but bear/bull scores only 43-50% exact, because no
  historical key-levels.json snapshot exists in the repo -- levels are approximated from the
  CURRENT key-levels.json (no-look-ahead filtered). To lift score parity toward 100%, start
  snapshotting key-levels.json daily (append-only, dated) so past replays inject the ACTUAL levels
  the live engine saw that day. Verdict/side are robust to the drift; this is a fidelity upgrade,
  not a blocker. depends:none :: status:pending

### DOJO-BUILD-HANDOFF (HIGH, Opus-tier build, filed 2026-07-20 ~21:45 ET -- J's idea, Fable-specced same evening)

- [ ] DOJO-BUILD-HANDOFF (HIGH, Opus builds Phase 1) :: J's replay-training-room program.
  The build prompt IS markdown/specs/DOJO-REPLAY-TRAINING-SPEC.md -- read it whole, build
  Phase 1 in its listed order (step 0: empirically test TV replay_* MCP tools on the
  CURRENT TradingView plan and document limits BEFORE J buys a tier). Two-lane harvest
  rule + no-live-state fence are load-bearing. Routing: Opus framework -> Sonnet runs
  sessions with J -> Fable adjudicates Lane-B harvests only. depends:none :: status:pending

> **NOT PICKABLE by a conductor fire (checked 2026-07-20 ~21:50-22:xx ET, AFTERHOURS):** step 0
> requires literally calling the TradingView `replay_start`/`replay_step`/`replay_status` MCP
> tools against the live TV desktop app (CDP port 9222) -- this conductor fire's bound tool set
> has zero TradingView MCP tools (only Alpaca account/position/clock + file/bash tools), confirmed
> by checking the actual available function list this session, not assumed. No CLI/script wrapper
> around the TV MCP server exists in-repo either (grepped for `replay_start` usage -- only
> mentions are in two automation prompt docs, no callable client). **This needs an interactive
> session with the TradingView MCP server wired** (J's own session, or a future agent invocation
> that has it bound) to actually run step 0 -- a conductor fire cannot self-escalate its own tool
> set mid-fire. Leaving `status:pending`, HIGH, at the top of the backlog is correct; just noting
> WHY it keeps getting skipped by AFTERHOURS/WEEKEND conductor fires specifically, so a future fire
> doesn't waste a cycle re-discovering the same tool-availability gap.
  **NOTE 04:57 ET 2026-09-03 (Fable):** still not pickable by a builder -- step 0 needs the live TradingView desktop + CDP (`replay_start`/`replay_step`/`replay_status` MCP tools) which are up only 08:00-16:00 ET via Gamma_LaunchTV; an interactive session in that window is barred by the RTH discipline. Runnable slot: a weekday 16:00-17:00 ET interactive session (TV still up, market closed) or J launching TV on a weekend. Left open; not a tonight item.

### DOJO-DEEP-RESEARCH (LOW, bounded, free/Sonnet) :: one research pass -- DAgger-style
  imitation learning from expert replay for trading policies; prop-firm bar-replay drill
  methodology; open-source trading replay trainers worth mining. Output: short notes doc
  feeding the DOJO build; does NOT gate it. depends:none :: status:pending

### DECISION-ROW-SPY-STALENESS (HIGH, sight-integrity investigation, filed 2026-07-20 ~18:30 ET from Lever-2 discovery)

> **CLOSED 2026-07-20 ~18:19-18:55 ET (conductor, AFTERHOURS): shipped, tested, committed
> `c593508`.** Found the fix already ~90% built + fully wired but UNCOMMITTED in the working
> tree from an earlier fire this session (16:08-16:17 ET timestamps on the new files) --
> this fire's job was VERIFY + FINISH + SHIP, not re-derive. **(1) Provenance answer:**
> `bc['bar']['close']` (== `trig['close']`, trig_idx=n-2 of the fetched 5m window) IS the
> field BOTH the trigger/scoring path AND the log use -- same value, single source, not two
> divergent fields. The lag (~5-10min, only advances once per 5m bar close) is BY DESIGN
> (no-look-ahead requirement, matches backtest fidelity) -- confirmed the separate
> `context_bundle.spy` field (context_bundle_producer.py) is genuinely log-only and does
> NOT feed score/gates (docstring + grep-verified, zero consumers on the score/_derive_tier
> path), so that field was a red herring; the REAL exposure is the trigger-bar's own
> structural lag becoming pathological when price moves fast inside the ~5-10min window --
> exactly what happened 07-20 09:51-09:55 (3 fleet vix_regime_dayside fills traded against
> a spot $0.40-$1.38 stale). **(2) Quantification**
> (`analysis/recommendations/decision-row-spy-staleness-2026-07-20.json`, n=3860 RTH rows
> 07-14..07-20): mean divergence 0.38, median 0.27 (expected structural lag), p99 2.49; real
> FILLS this week topped out at $0.63 divergence outside the 07-20 cluster, which alone hit
> $0.40/$1.12/$1.38 -- $1.00 threshold cleanly separates pathological from normal without
> touching a single other real entry. **(3) Fix shipped:** `_fetch_live_spy_quote()`
> (Alpaca `/trades/latest`, deliberately NOT another bar-close) +
> `_sight_staleness_check()` cross-check the trigger spot against a fresh tick-level read
> ONLY at the moment an ENTER is about to be attempted (primary path + extra-setup route),
> fail-open both directions (no live quote -> never blocks; divergence > $1.00 ->
> `SKIP_STALE_SIGHT`, no order attempted). `trigger_bar_et` now logged on every row
> (visibility). Guard: `backtest/tests/test_sight_staleness_guard.py` 23/23 green; adapted
> `test_gate_provenance_ordering_2026_07_10.py` + `test_money_path_2026_07_01.py` to pin
> `_fetch_live_spy_quote` (deterministic, never trips the new guard incidentally) -- 136/136
> heartbeat_core-adjacent tests green, zero regressions; pre-commit safety gate PASS.
> **Not addressed (separate, smaller, non-blocking):** the 09:34 `spy=743.28 ==
> prior-close` / `gap_reason="no_rth_bars_for_today_yet"` seam is a DIFFERENT field
> (context_bundle's daily-gap computation, not the trigger-bar spot this fix covers) --
> filed as a follow-up below, LOW, since it's a log-only fallback value this same
> investigation confirms is non-load-bearing. **PAPER accounts only, rail-4
> guard+revert+REVOKE:** revert = `git revert c593508`. REVOKE window open on Discord.
  **GRANULARITY GAP NOTED 13:03 2026-09-03:** the 07-20 fix addressed staleness; the `spy` field remains the last closed 5-MINUTE bar close by design (`heartbeat_core.py:1661`). Today's dissection fleet misread wave 1 as 'flat SPY, pure decay' from that field while the option quote tape showed a one-minute 30% gap at 10:00->10:01 ET (ISM Services). Filed RTH-SPY-PER-MINUTE-TAPE below. :: status:done

### GAP-REASON-SESSION-OPEN-FALLBACK (LOW, follow-up from DECISION-ROW-SPY-STALENESS close, filed 2026-07-20 ~18:55 ET)

### STRUCTURE-STOP-ZONE-BAND (HIGH, trading-path, filed 2026-07-20 ~14:50 ET during RTH -- FIX AFTER 16:00, Rule 9; J called the failure live)

> **CLOSED item (a) 2026-07-20 ~16:19-16:55 ET (conductor, AFTERHOURS): pre-reg A/B REJECT_ALL_CANDIDATES.**
> Ran `backtest/tools/structure_stop_zone_band_ab.py` (frozen pre-reg:
> `analysis/recommendations/structure-stop-zone-band-preregistration.json`, output:
> `analysis/recommendations/structure-stop-zone-band-2026-07-20.json`) -- isolated ONLY the
> buffer/band width on the existing trigger_level reference (the 2026-07-09 study's SS-A/B/C
> confounded buffer with tp1_premium_pct; this study held the LIVE SS-B shape fixed and swept
> buffer 0.00/0.05/0.08/0.10/0.12/0.15/0.20 alone). **REJECT_ALL**: every buffer >0 FAILS the
> dual-layer gate (fresh-slice layer(a) expectancy WORSE than the 0-buffer control for every
> single candidate, -47.9 to -52.34 vs -47.34 control) AND the real-fills anchor layer(b) "wins"
> that clear the bar (BAND-10/12/15/20, +$677 to +$801 vs -$900.7 control) are entirely an
> artifact of ONE 2026-07-08 signal (SPY260708P00741000, replicated across 4 arms, $532/388/331
> per-leg swing) -- the sub-window split (first half vs second half) shows a hard SIGN FLIP
> (+$1656-1736 first half vs -$34.5 to -$74.5 second half) for every passing candidate, the
> exact single-anchor-trade-driving-everything signature C24 warns about. Today's 3 exhibit
> fills were NOT recoverable via this study's fills-ledger source (0/0 -- a separate, disclosed
> data-path gap: `exit_shape_parity_study.load_fleet_engine_fills()` tops out 2026-07-17 despite
> `fills-ledger.jsonl` itself having 2026-07-20 rows -- worth a future fire's attention but not
> blocking here since the exhibit was informational-only by the pre-reg's own design). **Verdict
> confirms the queue item's own quantified counterfactual**: widening the SAME (trigger-exact)
> reference doesn't reproduce a stable edge -- it's the REFERENCE CHOICE (item b) that flips
> today's outcome, not the band width on the wrong reference. BAND-00 (today's live behavior,
> buffer=0) stays unchanged. Guard: `backtest/tests/test_structure_stop_zone_band_ab.py` (7/7,
> RED-proofed via file-move -- untracked file, `git stash` unsafe here, see below). Curated
> safety gate (31+5-suite) PASS. **Zero trading-path files touched** -- ANALYSIS ONLY, no
> `params.json`/`strategies.py`/`exit_manager.py`/placement/exit code edited; nothing to revert.
> **Blast-radius near-miss (recorded, not a lesson -- no code change needed):** attempted
> `git stash -- backtest/tools/structure_stop_zone_band_ab.py` (an UNTRACKED file) to RED-proof;
> the pathspec didn't match (untracked files need `-u`/`add` first), the command aborted with
> exit 1, and NOTHING was stashed -- confirmed via `git rev-parse stash@{0}^1` resolving to a
> 2026-07-18 commit (2 days stale, pre-existing from an earlier session, untouched by this fire).
> Recovery = none needed; switched to the file-move RED-proof technique (matches the
> SAFE-VIX-CONDITIONAL-SIZING 2026-07-20 precedent for untracked new modules) for the rest of
> this fire and going forward for any future untracked-file RED-proof.
  **THIRD REJECTION 13:03 2026-09-03 (dissect-zone-stop-semantics + this morning's H5):** today's wave 2 was a 4-cent raw-level breach with the zone floor never touched, followed by +$5 -- the exact live shape J called on 07-20. On the 79-event real structure-stop population a level-sized (zone_width) buffer nets +$4,076 but 107% of it is 3 positions and drop-best-day is -$841; fixed $0.15/$0.25/ATR/two-close/grace buffers all flip negative ex-best-day. Not shippable as a blanket rule; the forward instrument `Gamma_RetestZoneShadow` (registered 2026-09-03, prereg-retest-zone-grid) persists the zone width in force per trigger so the next test runs on real widths. Reports: `analysis/deep-research/2026-09-03-money/dissect-zone-stop-semantics.md`, `structure-stop-whipsaw.md`. :: status:closed-third-rejection

### STRUCTURE-STOP-REFERENCE-LEVEL (HIGH, trading-path, filed 2026-07-20 ~16:55 ET, follow-up to STRUCTURE-STOP-ZONE-BAND item (b))

> **CLOSED item (b) 2026-07-20 ~17:00-17:35 ET (Sonnet worker, AFTERHOURS): pre-reg A/B
> NO-SHIP, both candidates.** Answered SPEC question (1) affirmatively: `lib/levels.py`'s
> `LevelSet.active` (via `tw8_level_context.frozen_level_set_for_date`, the SAME per-day-
> frozen level set `lib/orchestrator.py`/`lib/filters.py` trade against) already carries
> the full multi-level structure per day, and `detect_level_reclaim`/`detect_level_rejection`
> already identify WHICH specific level fired -- no new data plumbing was needed to resolve a
> zone boundary. Built `backtest/tools/structure_stop_reference_level_ab.py` (new
> `resolve_zone_boundary`/`reference_level_for` pure functions + reuses
> `structure_stop_study.py`'s trigger recovery/replay machinery unchanged, per spec (2)/(3)),
> froze `analysis/recommendations/structure-stop-reference-level-preregistration.json` BEFORE
> running anything (band width held at 0.00 for every candidate by rule -- item (a) already
> falsified that axis; re-opening it here without reference-level evidence would be fishing),
> ran it, verdict: `analysis/recommendations/structure-stop-reference-level-2026-07-20.json`.
> **REF-ZONE** (nearest active level beyond the trigger, away from spot) FAILS layer(a)
> fresh-slice expectancy (-$63.73/tr vs -$47.34 control, n=18) -- worse, not better. Its
> layer(b) real-fills anchor "win" (+$481.2 vs -$900.7 control, n=68) is the SAME single-
> anchor-trade artifact C24 flagged in item (a): one 2026-07-08 position
> (SPY260708P00741000, 3 legs) accounts for the entire delta -- under REF-ZONE the structure
> stop simply never fires that day (zone boundary 745.21 vs entry-adjacent trigger 744.17,
> too far to matter) and the position rides to $427/$427/$307 vs -$105/+$20/-$81 under
> today's live reference -- and the sub-window split hard sign-flips (+$1473.4 first half vs
> -$91.5 second half). **REF-NONE** (no structure stop at all, pure premium-only SS-B) fails
> the SAME way, even worse on layer(a) (-$84.29/tr). **Verdict: NO-SHIP both candidates** --
> `automation/state/fleet/exit_manager.py`/`strategies.py` UNCHANGED, no
> `structure_stop_reference_mode` knob added (per the task's own gating: wiring only happens
> if a candidate clears; neither did). `backtest/lib/exit_manager_walk.py` faithful-harness
> replay (spec (4)) was correctly SKIPPED, not omitted -- that step is the SHIP-gate
> verification for a cleared candidate against the tick-managed live decision core; nothing
> cleared the exploratory pre-reg bar to reach it. Guard:
> `backtest/tests/test_structure_stop_reference_level_ab.py` (17/17, RED-proofed via the
> file-move technique -- untracked new module, `git stash` on an unmatched pathspec silently
> no-ops rather than stashing, per tonight's established precedent: moved the module out,
> confirmed `ModuleNotFoundError` on all 17, moved back, re-verified 17/17 green). Broader
> sweep (`test_structure_stop_study` + `test_structure_stop_zone_band_ab` +
> `test_structure_stop_reference_level_ab` + `automation/state/fleet/test_exit_manager` +
> `test_exit_actuator`) -> **113/113 PASS, 0 regressions**. **Both sub-fixes of the original
> STRUCTURE-STOP-ZONE-BAND queue item (band width, item a; reference choice, item b) are now
> tested and rejected under the same dual-layer discipline** -- the 2026-07-20 14:16 exhibit's
> own -$24 vs +$115-130 counterfactual remains a single anecdote (C24/L140) this study could
> not generalize into a population-level edge. Today's 3 fills were again NOT recoverable via
> this study's fills-ledger source (0/0, exhibit shows 0 positions) -- the same disclosed
> `load_fleet_engine_fills()` date-ceiling gap item (a) flagged, unfixed here (out of scope,
> flagged only). **Zero trading-path files touched.** Cost: ~$4 (1 pre-reg write, 1 new
> ~330-line study tool reusing existing machinery, 1 live run against real OPRA/fills data, 1
> guard-test file + RED-proof round-trip, 1 broader regression sweep, this queue/STATUS
> update). No commit made (orchestrator commits after verification per this fire's own rules).

> **CROSS-REFERENCE 2026-07-20 evening (fleet exit-parameter A/B build, separate fire):**
> `automation/state/fleet/accounts.json`'s risky-3 (FLEET-LOOSE-R) now carries a per-arm
> `params_patch.exit_patch` (new mechanism, `fleet_executor._exit_shape_dict` /
> `EXIT_PATCH_ALLOWED_KEYS`) meant to make this arm "ride it longer" than safe-3's
> chart-stop-primary lane. The IDEAL knob for that -- stop referenced to the zone boundary
> ABOVE the entry trigger, not the trigger itself -- is exactly item (b) above (REF-ZONE),
> which is NO-SHIP per tonight's own pre-reg A/B (single-anchor-trade artifact, sub-window
> sign-flip). Since that knob does not exist and is not currently evidence-backed, risky-3's
> exit_patch approximates "rides longer" with a wider chandelier trail (`trail_pct: 0.20` vs
> the registry's 0.15/0.125) on the SAME trigger-exact `stop_mode=structure` reference every
> other structure-stop position uses -- deliberately NOT re-opening the rejected REF-ZONE
> axis. If a future pre-reg A/B on a DIFFERENT reference-level formulation ever clears,
> revisit risky-3's exit_patch to use it instead of the trail-width proxy.

### EXTRA-SIGNAL-CHURN-COOLDOWN (HIGH, trading-path, filed 2026-07-20 ~11:25 ET during RTH -- FIX AFTER 16:00, Rule 9)

> **CLOSED item 1 (re-entry cooldown) 2026-07-20 ~16:42-17:15 ET (conductor, AFTERHOURS): SAME-BAR
> re-entry guard shipped, guard-tested, committed.** Traced the churn mechanism first: the
> extra-setup lane's watcher "current-bar guards" only stop a DUPLICATE signal firing twice --
> they never stop a FRESH entry attempt once the account goes flat again mid-bar (a stop-out),
> and `_route_extra_setups` had zero memory of "did this setup already try this bar." Chose
> **"requires-new-trigger-bar" over a hand-picked N-minute duration** (the item's own suggested
> alternative) specifically because this is a brand-new mechanism with no existing trade
> population to pre-register a numeric cooldown against -- the bar boundary is the smallest
> non-arbitrary unit available, so there is no knob to A/B here (unlike item 2 below, which DOES
> need one). **Built:** `exit_actuator.load_last_entry_bars` / `record_entry_bar` /
> `same_bar_cooldown_active` (new, `automation/state/fleet/exit_actuator.py` -- a per-arm,
> per-setup "last trigger-bar attempted" ledger, same persistence pattern as the existing
> `load_states`/`save_states` pair) + wired into `heartbeat_core._route_extra_setups`
> (`setup/scripts/heartbeat_core.py`): before any entry attempt, refuse it
> (`SKIP_COOLDOWN_SAME_BAR`) if the setup already attempted an entry on this EXACT trigger bar;
> record the bar on an actual PLACED/PLACING/WOULD_PLACE only (never on WATCH_NOT_ARMED /
> VETOED_BY_MODELS / SKIP_TICK_ENTRY_TAKEN). Fail-open throughout: a cooldown-file read/write
> error never blocks a legitimate entry. Scoped to the extra-setup lane only -- the primary
> ribbon path already has its own one-position-at-a-time + gate discipline and was out of this
> fix's scope. **Verified this fire:** new guard
> `backtest/tests/test_extra_signal_churn_cooldown_2026_07_20.py` (10/10) covers the round-trip,
> same-bar-blocks / different-bar-doesn't, fail-open on a cooldown-check exception, and
> record-only-on-actual-placement. RED-proofed via `git stash` on the 2 edited files (untracked
> new test file separately moved out and back, per the file-move technique this session's earlier
> fires established for untracked modules): stashing the 2 tracked files + moving the test file
> out reproduced the exact expected mechanism (`AttributeError: module 'exit_actuator' has no
> attribute 'load_last_entry_bars'`, 9/10 fail), `git stash pop` + move-back restored cleanly,
> re-verified 10/10 green. Broader sweep (`test_g4_extra_setup_routing` +
> `test_gap_and_go_exit_wiring_2026_07_18` + `test_audit_fix_heartbeat` + `test_audit_fix_exit` +
> `test_execute_stop_display` + `test_g14_fleet_ribbon_exit` + `test_money_path_2026_07_01` +
> `test_trade_to_learn_2026_07_01` + this file) -> **136/136 PASS, 0 regressions**. Curated
> safety gate (31+5-suite, `run_safety_gate.py`) PASS.
>
> **Rail-4 (PAPER trading-path -- guard test + revert path + this REVOKE report):** touches
> `automation/state/fleet/exit_actuator.py` (additive, 3 new functions, zero existing function
> bodies changed), `setup/scripts/heartbeat_core.py` (`_route_extra_setups` gains one new
> same-bar check before the existing veto/execute try-block + one recording call after a
> successful placement; zero change to the primary ribbon path, zero change to gate ordering,
> zero change to `_execute`'s pricing/sizing/placement logic), `backtest/tests/
> test_extra_signal_churn_cooldown_2026_07_20.py` (new guard), `automation/overnight/queue.md`
> (this closure). **Revert:** `git revert <commit>` (single pathspec commit, 3 files) -- purely
> additive, so a revert is a clean no-behavior-change rollback to today's exact pre-fix churn
> risk (the item's own live exhibit).
>
> **Item 2 (exit-shape misalignment) NOT fixed this fire -- re-filed below as
> `EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT`.** Confirmed live (not just claimed): `params.json`
> carries `j_vix_dayside_premium_stop_pct: -0.08` / `j_vix_dayside_tp1_pct: 0.3` (the exact
> old-shape numbers the item cites), routed through `_SETUP_EXIT_OVERRIDES["vix_regime_dayside"]`
> in `heartbeat_core.py` -- confirmed still live and unchanged since 2026-06-18's core-lane
> chart-stop-primary shift, exactly as the item alleged. Did NOT flip it this fire: changing a
> live exit-stop knob without a pre-reg A/B against real fills would violate C29 (exit knobs
> ratified on one tier/setup don't transfer to another -- there is no existing validated
> chart-stop cell for `vix_regime_dayside` to fall back to, unlike `gap_and_go`'s already-
> validated shape) -- a blind widen is exactly the kind of "hand-picked knob" OP-16/C29 forbid.

### EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT (MED, trading-path, needs pre-reg A/B, filed 2026-07-20 ~17:10 ET, item 2 of EXTRA-SIGNAL-CHURN-COOLDOWN)

- [ ] EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT (MED, after-hours study + pre-reg A/B) :: The
  `vix_regime_dayside` extra-setup lane (and by inspection every OTHER `_SETUP_EXIT_OVERRIDES`
  entry except `gap_and_go`) still trades its ORIGINAL 2026-06-01-era premium bracket
  (`j_vix_dayside_premium_stop_pct=-0.08` / `j_vix_dayside_tp1_pct=0.30`) -- confirmed live in
  `params.json` 2026-07-20. The 2026-07-08 noise-floor study found -8% premium stops on 0DTE
  read as spread/quote noise more than real invalidation (10-min MAE -36% vs -20% stop = winners
  stopped by noise, per the standing memory `project_noise_floor_entry_exit_matrix`); the core
  ribbon path moved to chart-stop-primary on 2026-06-18 for exactly this reason, but the
  extra-setup lane's per-setup overrides were never revisited after that shift. FIX (needs a
  REAL pre-reg A/B before any params flip -- C29: exit knobs validated on one setup/tier don't
  transfer to another without independent evidence):
  (1) pull `vix_regime_dayside`'s (and the other 3 non-gap_and_go overrides') own fills history
  from `fills-ledger.jsonl` + `core-decisions.jsonl` (small-n expected -- these are newer/rarer
  extra-setup lanes than the core path, so this may be an underpowered-n<15 DISCLOSE-not-hide
  case per C13, not a block on running the study);
  (2) pre-register a widened-stop candidate (e.g. -20%/-30%, matching the core lane's pre-SS-B
  premium-stop era, NOT a guess -- cite the specific historical value being reused) vs the
  current -8% control, same dual-layer (fresh-slice expectancy + real-fills anchor) + sub-window
  stability discipline the STRUCTURE-STOP-ZONE-BAND study used (reuse its machinery where the
  setup shape allows);
  (3) if n is too small for a real verdict, the honest conclusion is DEFER-INSUFFICIENT-DATA,
  not a blind flip -- do not hand-pick a replacement value absent evidence just because -8% is
  suspected to be too tight;
  (4) if/when a candidate clears the auto-ratify gate (OOS+/WF>=0.70/sub-window-stable/anchor-
  no-regression), ship it exactly like any other trading-path change (guard test + revert path +
  REVOKE report, rail 4) -- this item does NOT need J's ratification, only real evidence.
  Evidence: `automation/state/params.json` (`j_vix_dayside_premium_stop_pct`/`_tp1_pct`),
  `setup/scripts/heartbeat_core.py::_SETUP_EXIT_OVERRIDES`, the EXTRA-SIGNAL-CHURN-COOLDOWN
  closure note above (this fire's live confirmation).
  depends:none :: status:pending

> **STEP (1) DONE for `vix_regime_dayside` only, 2026-07-20 ~evening (after-hours, AUDIT-ONLY --
> no params/stop-shape change made): pulled the lane's fills history and it is thinner than
> even this item anticipated.** `core-decisions.jsonl` scan of every `extra_exec` row with
> `setup=="vix_regime_dayside"` (14 rows total across the lane's whole life) shows exactly
> **3 PLACED entries ever** -- and all 3 are TODAY's churn exhibit (09:51/09:54/09:55).
> Every earlier attempt (2026-07-02, 2026-07-09) was blocked at `RISK_DENY_RISK_CAP` /
> `RISK_DENY_PDT` before ever reaching the broker. **Today is this lane's first-ever live
> fill, so n=3 is not a sample of the lane's history -- it IS the lane's entire history.**
> Per-trade detail (`fills-ledger.jsonl`, symbol `SPY260720C00748000`, arm `safe-2`; NBBO +
> `spy` spot from the matching `core-decisions.jsonl` ticks):
>
> | # | entry fill | stop fill | hold | entry NBBO spread | -8% stop distance | spread/stop-distance | SPY spot entry-tick -> exit-tick |
> |---|---|---|---|---|---|---|---|
> | 1 | 09:51:24.73 @ 1.13 | 09:52:03.56 @ 0.98 | 38.8s | $0.00 (bid=ask=1.10) | $0.088 | 0% | 747.575 -> 747.575 (unchanged) |
> | 2 | 09:54:19.66 @ 0.79 | 09:55:03.98 @ 0.73 | 44.3s | $0.04 (0.76/0.80) | $0.0624 | **64%** | 747.575 -> 747.575 (unchanged) |
> | 3 | 09:55:24.87 @ 0.76 | 09:56:03.44 @ 0.68 | 38.6s | $0.02 (0.72/0.74) | $0.0584 | 34% | 747.575 -> 746.43 (real -1.145pt move) |
>
> **Reading:** 2 of 3 stop-outs (trades 1+2) fired while the engine's OWN logged SPY spot was
> IDENTICAL at entry and exit -- zero observed underlying movement across the full hold, i.e.
> the -8%/-6% premium move that triggered the stop has no price-action justification in the
> engine's own record; trade 2's entry-time NBBO spread alone ($0.04) consumed **64% of its
> entire stop distance** ($0.0624), meaning roughly two-thirds of that stop's margin was spread,
> not room. Trade 3 is the one case with a real, contemporaneous SPY move against the position
> (-1.145pts) -- closer to a legitimate invalidation, though its spread (34% of stop distance)
> was still non-trivial. This is DIRECTIONALLY CONSISTENT with the 2026-07-08 noise-floor
> finding (the same mechanism the core lane moved off of on 2026-06-18) but **n=3, all from one
> session, is not a verdict** -- exactly the DEFER-INSUFFICIENT-DATA condition this item's own
> step (3) pre-committed to. Caveat for whoever runs steps (2)-(4): SPY spot pinned at EXACTLY
> 747.575 for 4 consecutive 1-minute ticks (09:51-09:55) is itself worth independently checking
> for a stale/frozen quote snapshot in the engine's log before leaning on the "flat SPY" reading
> too hard -- if it's a live-feed artifact rather than genuine chop, only the spread-ratio numbers
> (0%/64%/34%) stand on their own, which still lean noise-consistent for trade 2 specifically.
> **No stop-shape change made** (per this item's own gate + this fire's instructions) -- this is
> disclosure to sharpen steps (2)-(4), not a substitute for them; the other 3 non-`gap_and_go`
> overrides named in step (1) are still unpulled (out of this fire's scope, which was
> `vix_regime_dayside` only). Status stays `pending` -- the real pre-reg A/B still needs more
> organic n than one session can supply.

> **EVIDENCE ADDED 2026-07-20 ~evening (after-hours, REPORT-ONLY -- no params/stop-shape
> change): counterfactual replay of ALL 11 `exit_stage=premium_stop` episodes (2026-07-13..
> 07-20, `analysis/winning-trade-map/episodes-2026-07-13-to-2026-07-20.json`) under RIBBON_
> RIDE's chart-stop-primary shape** (`backtest/tools/extra_signal_premium_stop_counterfactual.py`
> -> `analysis/recommendations/extra-signal-premium-stop-counterfactual-2026-07-20.json`),
> driven through the REAL `exit_manager.plan_exit_actions` over real 1-min SIP(SPY)/OPRA
> bars fetched fresh this fire. **Result: NET WORSE, not better** -- actual $-509.00 vs.
> counterfactual $-601.01 (delta **-$92.01**). Per-episode: 2/11 clearly better (+$78/+$33,
> both the SAME vwap_continuation 07-16 09:51-09:53 lane -- noise-floor-consistent), **3/11
> clearly WORSE** (-$63/-$84/-$27 -- real, continuing adverse SPY moves that the -50%-
> catastrophe-adjacent shape let bleed further before catching), 5/11 roughly neutral
> (+/-$15), 1/11 an exact fidelity-match (E4, already running structure mode live in
> production). **CAVEAT CORRECTED against this run's own evidence:** the "a losers-only
> cohort can only look better-or-equal under a looser stop" argument this item's framing
> assumed does NOT hold for an exit-SHAPE-SWAP (vs. an entry-filter-removal) counterfactual
> -- chart-stop-primary is not a pure loosening (its -50% cap is wider than these lanes'
> native -6%/-8% brackets), and this run's own 3 worse-outcomes refute the "can't look
> worse" premise directly. **STALE-QUOTE caveat (flagged in the STEP(1) note above) RESOLVED:**
> confirmed a STALE-FEED ARTIFACT in the DECISION CONTEXT LOG only (context_bundle computed
> once at 09:50:02, reused across the 09:51/09:54/09:55 ticks) -- the real 1-min SIP tape
> shows SPY genuinely sold off 747.62->746.14 (~$1.48, 100K-265K shares/min) over that
> window; contaminates only those 3 episodes' logged alignment/levels context, not this
> replay (reads real bars directly). **Verdict: DEFER-INSUFFICIENT-DATA** -- n=11 across 3
> sessions and effectively 2 true shape-swap lanes (vix_regime_dayside's n=3 is one
> session's entire history; bollinger_squeeze/vwap_continuation each n<=3), exactly this
> item's own step-3 pre-committed condition. Status stays `pending` -- this evidence neither
> supports shipping the alignment nor rejects it; steps (2)-(4)'s real pre-reg A/B still
> needs organic n this after-hours fire cannot manufacture.

### PREMARKET-TOUCH-CREDIT-STUDY (HIGH, study-first, filed 2026-07-20 ~09:36 ET, J question same morning)

> **CLOSED 2026-07-20 ~17:15-18:05 ET (conductor, AFTERHOURS): KILL, pre-registered and run
> in full.** Froze `analysis/recommendations/premarket-touch-credit-preregistration.json`
> BEFORE any replay. Built `backtest/tools/premarket_touch_credit_study.py`, reusing
> `structure_stop_study.py`'s replay engine (SS-B, trigger-exact, buffer=0.00 -- confirmed
> literal live behavior per tonight's structure-stop studies), `tw8_level_context.py`'s
> frozen per-day level set, and `lib.filters.detect_level_rejection`/`detect_level_reclaim`
> (the EXACT production bar-test, direction-matched to side) reused verbatim for premarket
> touch detection -- zero new hand-picked band/proximity parameter. Fresh-slice population:
> 41 signals combined from the canonical 2025-2026 signal cache (filtered to the Alpaca-SIP-
> verified premarket window 2026-05-19..2026-07-17, per DATA-PROVENANCE.md -- older dates
> excluded by rule to avoid an IEX/09:00-start feed provenance confound) + the existing 18-
> signal FRESH_SIGNAL_SET, deduplicated; 27 had a recoverable trigger_level and cached option
> bars (0 network calls -- all local cache, $0). **Result: n_touched=15 (SS-B expectancy
> -$15.88/tr), n_untouched=12 (-$302.50/tr), observed delta +$286.62 favoring premarket-
> touched levels -- directionally consistent with J's own reading, but NOT statistically
> distinguishable from noise**: random-label permutation null p=0.21 (2000 draws), shuffled-
> level null p=0.208 (500 draws/segment) -- neither survives BH-FDR at alpha=0.05 (both
> False). **Verdict: KILL**, exactly the pre-reg's own disclosed-in-advance expected outcome
> for an n~27 population. Layer (b) real-fills anchor (live OPRA re-fetch) was DEFERRED by
> the pre-reg's own scope_note -- not worth ~$4 of network calls to confirm a KILL that layer
> (a) alone already resolves; no follow-up study needed unless a future, larger fresh-slice
> population (e.g. once the canonical signal cache is rebuilt through a later END date)
> reopens the question with more power. **Guard:**
> `backtest/tests/test_premarket_touch_credit_study.py` (26/26: BH-FDR against a classic
> textbook example, direction-matched touch detection incl. no-cross-day-leakage and no-RTH-
> bar-leakage, segmentation math, verdict-ladder branch coverage, live pre-reg/output sanity),
> RED-proofed via the file-move technique (untracked new module -- moved out, confirmed
> `ModuleNotFoundError` on all 26, moved back, re-verified 26/26 green). Broader sweep
> (`test_structure_stop_study` + `test_structure_stop_zone_band_ab` +
> `test_structure_stop_reference_level_ab` + this file) -> **72/72 PASS, 0 regressions**.
> Curated safety gate (31+5-suite) PASS. **Zero trading-path files touched** -- ANALYSIS ONLY,
> no `heartbeat_core.py`/level_states/`params.json`/any placement/exit code edited; nothing to
> revert; no wire attempted (per the item's own "NOT a same-day wire" scope -- KILL means
> there is nothing to wire). Files: `analysis/recommendations/premarket-touch-credit-
> preregistration.json`, `analysis/recommendations/premarket-touch-credit-2026-07-20.json`,
> `backtest/tools/premarket_touch_credit_study.py`,
> `backtest/tests/test_premarket_touch_credit_study.py`, this queue.md entry. Cost: ~$4.5
> (STAGE 0/1 reads + task selection, machinery survey across levels.py/filters.py/
> tw8_level_context.py/structure_stop_study.py/probe_stats.py/_signal_cache.py, 1 pre-reg
> write, 1 ~330-line study tool, 1 local run (0 network calls), 1 new 26-test guard file +
> RED-proof round-trip, 1 broader 72-test regression sweep, 1 curated safety gate run, 1
> queue.md closure).

### SIM-EXIT-SHAPE-PARITY-AUDIT (MED, spec-only, filed 2026-07-17 ~22:47 ET, GOAL-REPLAY-TODAY-GREEN iteration 7)

- [ ] SIM-EXIT-SHAPE-PARITY-AUDIT (MED, spec-only, systematic re-check) :: Iteration 6
  (GOAL-REPLAY-TODAY-GREEN) found `simulate_trade_real` callers read exit knobs from
  `params.json`'s top-level keys (`profit_lock_mode="fixed"`, `tp1_premium_pct=0.5`, ...)
  instead of the REAL exit_manager's `automation/state/fleet/strategies.py#RIBBON_RIDE.exit`
  shape (`profit_lock_mode="trailing"` chandelier, `stop_mode="structure"`) -- every
  sim-based ribbon_ride exit study built on `simulate_trade_real` has been testing the WRONG
  exit shape, not an approximation of the right one. Iteration 7 rebuilt ONE affected study
  (`elite_bear_level_reject_gate_ab.py` / L1) under the correct shape via
  `backtest/tools/regime_readjudication_correctexit.py` and found a MATERIAL mechanism
  change: 13/16 removed trades were artificially flattened to exactly $0.00 under the wrong
  shape (profit-lock breakeven-round-trip artifact); under the correct shape the same cohort
  nets +$2,629.30/16 trades (10W-6L) -- a genuinely profitable population the wrong sim was
  hiding. The ship decision didn't change (still NO-SHIP, now on harder concentration-
  independent grounds) but the MECHANISM did -- for OTHER `simulate_trade_real`-based studies
  in this codebase, a similar correction could plausibly change ship decisions, not just
  mechanisms. Code-traced this iteration (NOT re-run, out of this goal's scope):
  `bold_strike_axis_deltawf.py`/`bold_strike_axis_ab.py` (uses
  `structure_stop_study.SS_B_SHAPE` via `plan_exit_actions` directly -- NOT the bug, but
  TRENDLINE-tier entries fall back to a -50% premium stop vs live's -20%, a narrower disclosed
  gap never independently verified), `zone_rejection_band_study.py` (same SS_B_SHAPE lineage),
  `pong_resting_limit_study.py` (bespoke `plan_exit_actions`-driven grid, paired-delta so
  common-mode shape errors mostly cancel -- but never formally verified). Grep
  `backtest/tools/*.py` for `simulate_trade_real` (16 files as of 2026-07-17, listed in
  iteration-7's session notes) and classify each: (a) genuinely affected (params.json-sourced
  shape feeding a ribbon_ride/live-strategy population -- rebuild via `exit_manager_walk.py`
  per the iteration-7 pattern), (b) already immune (drives `plan_exit_actions` directly, or
  studies a non-ribbon_ride strategy where the bug doesn't apply), (c) low-stakes/exploratory
  (smoke tests, one-off sweeps not feeding a ship decision). Ship-decision-bearing studies in
  bucket (a) get priority. Evidence:
  `automation/overnight/GOAL-REPLAY-TODAY-GREEN.md` ITERATION 7,
  `analysis/recommendations/regime-readjudication-correctexit-2026-07-17.{json,md}`.
  :: depends:none :: status:proposed

### ADVERSE-EXTREME-AVOIDANCE-FILTER (MED, pre-reg spec, from FAVORABLE-EXTREME-ENTRY-2026-07-17 KILL)

- [ ] ADVERSE-EXTREME-AVOIDANCE-FILTER (MED, spec-only, filed 2026-07-17 evening) :: The
  favorable-extreme-entry study (KILL, `analysis/recommendations/favorable-extreme-entry-2026-07-17.{json,md}`)
  produced ONE genuinely actionable positive signal as the MIRROR of its main finding: across
  BOTH real-fill populations (primary n=30 broker fills, secondary n=119 trades.csv), the
  **adverse_extreme entry-location bucket is the WORST** (primary -$17.87/tr 13% win; secondary
  -$8.98/tr 6.9% win) -- a marketable fill that lands at the WRONG end of its entry bar (put filled
  near the bar LOW, call near the bar HIGH) correlates with losing. This is a DIFFERENT, simpler
  mechanism than the resting-limit targeting that got killed: not "rest and wait for a favorable
  fill" (that loses clean runners + gets run over on trending days, 0/18 cells cleared anchor+BH-FDR
  both accounts), but "AVOID/deprioritize an entry whose actual marketable fill is adverse-extreme."
  Spec: pre-registered A/B of a post-fill (or at-fill, if a live-tick location read is available in
  the heartbeat) gate that skips or down-weights entries landing in the bottom-30%-of-bar-toward-the
  -wrong-side bucket, on the SAME confirmation-trigger signal population, real-OPRA replay, frozen
  `ab_delta_per_trade_v2026_07_16` WF form + BH-FDR + anchor, both accounts per C29. Open question the
  spec must resolve: is the fill-location knowable EARLY ENOUGH to act (the heartbeat samples SPY at
  the decision tick, ~<=60s before the broker fill -- verify whether that read is a good enough proxy
  for where the fill will land, or whether this is only a post-hoc diagnostic with no live actuation
  point). **SPEC REQUEST, do not wire without a cleared A/B (OP-16 eval-first).** Evidence:
  `analysis/recommendations/favorable-extreme-entry-2026-07-17.md` Synthesis + Build-spec sections.
  :: depends:none :: status:proposed

### SAFE3-RISKY1-GATE-RETEST-EXTEND (MED, needs pre-reg accrual, discovered 2026-07-17)

### TV-MCP-GETCHARTAPI-FIX-VERIFY (MED, fix landed, verify pending restart, 2026-07-14)

- [ ] TV-MCP-GETCHARTAPI-FIX-VERIFY (MED) :: G3 root-caused + fixed the `draw_list`/
  `draw_remove_one`/`draw_get_properties`/`draw_clear` "`getChartApi is not defined`" bug (the
  same one trendline-draw's Step 1 works around via `ui_evaluate` JS-injection). ROOT CAUSE:
  `src/core/drawing.js` in the reservoir repo
  (`C:/Users/jackw/Desktop/SwjshAlgoKnife/mcp-servers/tradingview-mcp`) â€” `listDrawings`,
  `getProperties`, `removeOne`, `clearAll` referenced the bare `getChartApi`/`evaluate`
  identifiers, which are only module-imported under the aliases `_getChartApi`/`_evaluate`;
  `getChartApi`/`evaluate` were never bound in those 4 functions' scope (only `drawShape` called
  `_resolve(_deps)` to bind them locally) â†’ ReferenceError before ever reaching CDP. FIX: all 4
  now call `_resolve(_deps)` first, matching `drawShape`'s existing pattern. Verified via a new
  mocked-`_deps` regression suite (`tests/drawing_getchartapi.test.js`, 5/5 pass, incl. a static
  source-audit guard that fails CI if a future function calls `getChartApi()`/`evaluate()`
  without resolving `_deps` first) â€” see that repo's `git diff src/core/drawing.js`.
  **NOT YET LIVE-VERIFIED end-to-end** â€” the running `tradingview` MCP server process
  (`src/server.js`, spawned per-Claude-session via `.mcp.json` â†’ `launcher.cjs`) has the OLD
  code cached in its already-running Node process; it re-reads from disk only on next spawn. No
  destructive action needed and no restart script to run by hand â€” the fix auto-applies the
  moment the NEXT fresh Claude Code session connects to the `tradingview` MCP server (new
  process = fresh `require`/`import`). **Do NOT force-kill/restart THIS session's live MCP
  process during market hours (09:30-15:55 ET) â€” that's the live CDP session J may be charting
  on.** Action for the next after-close (16:05+) or next-morning session: call
  `draw_list` / `draw_get_properties` / `draw_remove_one` for real against the live chart and
  confirm no `getChartApi is not defined`; if clean, trendline-draw's `ui_evaluate` JS-injection
  workaround (Step 1) can be retired in favor of the native tools â€” that's the OTHER audit
  crew's file (`trendline-draw/SKILL.md`), flag it to them / do it next session, don't edit it
  from this queue item. Also note: that reservoir repo currently has OTHER uncommitted changes
  (`src/connection.js` disconnect/error-handler additions, `src/server.js`
  unhandledRejection/uncaughtException handlers, `package-lock.json`) not made by this session â€”
  unrelated to the getChartApi fix, left as-is (not mine to commit/revert). :: depends:none ::
  status:pending

### PANDAS-CONSOLE-LEAK-ROOT-CAUSE (LOW, cosmetic-but-unresolved, discovered 2026-07-14)

- [ ] PANDAS-CONSOLE-LEAK-ROOT-CAUSE (LOW, mitigated not fixed) :: `import pandas` (pulls in
  numpy) under `backtest\.venv\Scripts\pythonw.exe` triggers a `WindowsTerminal -Embedding`
  console-host window on Win11, reproduced live via clean isolated `Start-ScheduledTask` fires.
  Ruled out as the trigger (all tested live, all failed to prevent it): launcher mechanism
  (`Shell.Run` vs `WshShell.Exec` vs Python `subprocess.Popen(creationflags=CREATE_NO_WINDOW)`),
  Python-level `sys.stdout`/`stderr` redirection, OS-level `os.dup2` fd redirection,
  `warnings.filterwarnings("ignore")`. A minimal stdlib-only script under the same interpreter
  is clean. Currently MITIGATED (not fixed) via `window-leak-detector.py` auto-hiding any
  service-rooted console-host window within its 0.5s poll â€” see STATUS.md 2026-07-14 entry for
  full investigation trail. If picked up again: try isolating numpy alone vs pandas-minus-numpy
  (not yet split), check for an explicit `ctypes.windll.kernel32.AllocConsole()` call anywhere
  in the installed numpy/pandas wheel's `.pyd`/`.dll` set, try `MKL_NUM_THREADS=1`/disabling
  MKL threading-layer auto-detection if this numpy build is MKL-linked (unconfirmed â€” check
  `numpy.show_config()`), or try a different numpy/pandas version pin as an A/B. :: depends:none
  :: status:pending
  **ROOT-CAUSED 04:12 ET 2026-09-03 (Sonnet bisection, Fable read) -- pandas was never the trigger:** a zero-import control script leaks identically under the venv's `pythonw.exe`. Mechanism: `backtest\.venv\Scripts\pythonw.exe` is CPython's `venvwlauncher` redirector, but `pyvenv.cfg` records only `executable=...\python.exe` (no GUI-variant path), so every venv `pythonw` launch re-execs the base CONSOLE `python.exe`, which spawns `conhost.exe` (verified via the live Win32_Process tree). The base install's own `pythonw.exe` never leaks. Stale 'pandas/numpy' comment in `window-leak-detector.py` corrected; guard test pins that the pandas import and the control script behave identically. Real fix touches the scheduler launch chain -- filed VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON. :: status:root-caused

- [ ] VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON (MED, infra, after-hours, filed 2026-09-03 04:12 ET from PANDAS-CONSOLE-LEAK-ROOT-CAUSE) :: every scheduled task that launches `backtest\.venv\Scripts\pythonw.exe` actually runs the base console `python.exe` (venvwlauncher + single-`executable` pyvenv.cfg), spawning a conhost per fire -- the true source of the window-leak rows. Options: (a) launch the base install's `pythonw.exe` with the venv activated via `PYTHONPATH`/`VIRTUAL_ENV` + `site` (the hidden-launch chain `run_cmd_hidden.py` already sets CREATE_NO_WINDOW; verify whether that alone suppresses conhost when the redirect happens inside the child); (b) add `executable_w` / use `python -m venv --upgrade` on a CPython build that records the GUI path; (c) leave as-is and rely on CREATE_NO_WINDOW. Measure first: count window-leak rows attributable to venv-pythonw launches over 7 days from `window-leaks.jsonl`; if (a) works on one non-trading task (e.g. Gamma_FeeRecalibrate), roll it through the install scripts in one after-hours pass with the leak detector as the oracle. Not during the trading day. :: depends:none :: status:partial -- MEASURED + 2 CONVERTED 18:57 ET 2026-09-03. Measurement (7 days, 418 leak rows, joined to run-cmd-hidden launching lines): 66.3% attributable to venv-pythonw launches (top sources futures_mirror_shadow 104, futures_health 82, state_freshness_remediate 38); the 33.7% UNATTRIBUTED bucket is a structural blind spot -- the install pattern is a TWO-hop chain and run_cmd_hidden.py logs only the inner hop, so the true share is higher. Converted to the base-pythonw + --env recipe with live-fire proof (script ran, output stamp advanced, zero new leak rows, pandas fine): install-retest-zone-shadow.ps1, install-structure-classifier-shadow.ps1 (fee-recalibrate was already on it). Guard test_venv_launch_recipe now carries a ROLLED_OUT allowlist. REMAINING: 54 installers still on venv-pythonw (43 shadow/analysis-class + 11 futures/broker-adjacent, named in the agent report) -- next after-hours pass, one at a time with the leak detector as oracle; trading-critical tasks (HeartbeatCore, FleetExecutor, EodFlatten*, Premarket, LaunchTV, TvWatchdog, SightBeacon) deliberately untouched and need their own pass.
  **RECIPE PROVEN 04:26 ET 2026-09-03 (Sonnet, Fable-verified):** 7-day attribution of `window-leaks.jsonl` (493 rows): 222 (45%) venv-pythonw attributable, all 13 unmitigated-at-capture rows were venv-pythonw. Live Win32_Process proof: CREATE_NO_WINDOW on the outer Popen does NOT survive venvwlauncher's internal re-exec (base console `python.exe` + `conhost.exe` appear); the base install's `pythonw.exe` spawns none. Recipe (a) trialled on `Gamma_FeeRecalibrate` only: inner target = base `pythonw.exe` with `run_cmd_hidden.py --env VIRTUAL_ENV=... --env PYTHONPATH=<venv>\Lib\site-packages` (PATH untouched) -> `pandas.__file__` resolves to the venv copy, zero console descendants, zero new leak rows, rc=0, `fee-calibration.json` refreshed. Recipe documented in the install script's WIRING comment; guard `test_venv_launch_recipe_2026_09_03.py` (6) pins it and asserts no sibling script picked it up unreviewed. NOT rolled to other tasks. Roll-out = a separate after-hours pass, one install script at a time with the leak detector as oracle, trading chain last. :: status:recipe-proven

### MCP-DAILY-AUDIT-CLAUDE-AUTH-FAILING (LOW, pre-existing, discovered 2026-07-14)

- [ ] MCP-DAILY-AUDIT-CLAUDE-AUTH-FAILING (LOW, pre-existing 2+ days) :: `Gamma_McpDailyAudit`
  (`run-mcp-daily-audit.ps1` -> `Invoke-Claude` haiku call) has failed `exit=1` for at least
  2026-07-13 (`API Error: 400 All target providers failed`) and 2026-07-14 (`Not logged in â€”
  Please run /login`) â€” different error each day, both pointing at the `claude` CLI / CCR
  routing layer, not this task's own logic. Confirmed NOT a regression from the same-day
  popup-storm fix (the task's launcher chain was rewrapped this session but the failure
  predates that edit by a day, same error family). Likely related to the CCR interactive-path
  hijack saga documented in this same file's `Gamma_CcrKeepalive` row (2026-07-14 lockout root
  cause) â€” worth checking whether the interactive-settings guard fully covers this task's own
  `claude --print` invocation path too. :: depends:none :: status:pending

### SWJSHAK-RUN-KEY-BARE-POWERSHELL (LOW, cross-project, discovered 2026-07-14)

- [ ] SWJSHAK-RUN-KEY-BARE-POWERSHELL (LOW, cross-project, ask before touching) :: Two
  SwjshAlgoKnife-owned HKCU `...\Run` entries (`SwjshAK-SystemStart`, `SwjshAK-HALOWatchdog`)
  use bare `powershell -WindowStyle Hidden -Command "..."` â€” same Win11 OpenConsole-before-
  hidden flash class fixed for Gamma's own tasks this session, but only fires once per boot
  (not a repeating-popup pattern) and SwjshAlgoKnife is scope-frozen (ask before expanding) so
  left untouched pending J's go-ahead. Fix (if wanted): repoint the Run-key command string at
  `wscript.exe //nologo "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden_exec.vbs"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "..."` (or an equivalent .vbs
  living in SwjshAlgoKnife's own tree, if J prefers not to cross-reference the 42 repo from a
  registry key in another project). Separately, `OpenClaw Gateway.cmd`
  (`%APPDATA%\...\Startup\`, `start "" /min cmd.exe ...`) is a genuinely unrelated third-party
  tool outside both projects â€” flagged only, no fix proposed. :: depends:J-go-ahead
  :: status:pending

### SHADOWEVAL-WEEKLY-TRIGGER-VS-DAILY-DOCS (LOW, doc/reality mismatch, discovered 2026-07-14)

### REPLAY-FLEET-ARMS-FIDELITY-DRIFT (MED, silently-red guard, discovered 2026-07-11)

### STRIKE-TIER-RECONCILIATION-FOLLOWUP (MED, doctrine-cleanup + open decision, 2026-07-11)

### PROFIT-P2-ARMED (MED, engine-edge, paper/J-revocable, 2026-07-11)

- [ ] PROFIT-P2-ARMED (MED, engine-edge, paper/J-revocable, 2026-07-11) :: Core Safe ribbon_ride strike OTM-2 -> ATM SHIPPED (`analysis/recommendations/ribbon-ride-strike-exit-ab.json`, ATM vs OTM-2 clears OP-11 auto-ratify: +$47.96/tr, delta-OOS +$8,574, WF 4.25, BH-FDR survivor, OTM-1/ITM-2 both fail their own gates -- not armed). Mechanism: added ribbon_ride's 2 entry_setups to `heartbeat_core.py`'s `_SETUP_STRIKE_OVERRIDES` dispatch (mirrors the WP-5 pattern exactly; new keys `params.json#j_ribbon_ride_strike_override_enabled`/`_strike_offset_safe`). Full REVOKE-report + consumer table: `automation/overnight/STATUS.md` 2026-07-11 entry. **DORMANT on the core lane** (safe-2 account deleted, pending J's replacement) â€” **the live safe-* fleet arms (safe-1/safe-3) do NOT inherit this key at all** (fleet_executor.py's strike selection is a wholly separate mechanism, `_tiers_for_arm` -> `crypto/lib/strike_selection.py#V15_SAFE_TIERS`, zero per-setup dispatch) â€” net Monday behavior change is ZERO either way. Forward-watch items: (1) once J's replacement core account lands, re-verify the override is still armed and actually firing; (2) decide whether fleet_executor.py needs its own per-setup strike dispatch to actually capture this edge on the live fleet arms (currently it cannot, structurally); (3) a SEPARATE open finding was surfaced (not fixed, spawned as its own task): `crypto/lib/strike_selection.py#V15_SAFE_TIERS` is already ATM/ATM for the $0-2K/$2K-10K bands, which does not match `params.json#v15_strike_offset_per_tier`'s own OTM-3/OTM-2 ladder or the CLAUDE.md tier-table prose. Revert: set `j_ribbon_ride_strike_override_enabled` false. **CONVENTION-AUDITED 2026-07-15 ~01:20 ET (see STRIKE-AB-CONVENTION-RECONCILIATION below):** the +$47.96/tr arming evidence had zero friction modeled; re-run under honest friction (SS-B fixed) still clears ATM-beats-OTM-2 at +$50.52/tr AND ATM is uniquely the only strike tier that clears positive expectancy overall + both-halves-stable -- arming stands, no revert indicated. :: depends:none :: status:armed-forward-watch

### BROKER-CANARY-SENTINEL-HOOKUP (LOW, one-line wiring, ready-now, 2026-07-11)

> **CLOSED 2026-07-20 ~20:15-20:45 ET (conductor, AFTERHOURS): wired, guard-tested, committed
> `3332454`.** Added the one-line call to `crypto_twin_health.main()` (the CLI entrypoint
> `Gamma_CryptoTwin`'s scheduled task actually invokes every 5 min) rather than into
> `run_tick_with_health()` -- that function has 34 existing tests with zero network mocking,
> and `probe()`'s leg 1 (unauthenticated crypto bars) is a REAL HTTP call; wiring it there
> would have made the entire existing test suite silently network-dependent. `main()` had
> zero prior test coverage, so this is a strictly additive change with no blast radius to an
> already-tested surface. Belt-and-suspenders `try/except` around the call site on top of
> `probe()`'s own internal fail-open guarantee (its own docstring: "never raises") -- a canary
> failure can never change the tick's own exit code or logged action. **Verified this fire:**
> 2 new tests (`test_main_calls_broker_canary_probe`, `test_main_survives_a_broker_canary_exception`)
> RED-proofed via `git stash` on both files -- both failed with the exact expected
> `AttributeError: module 'crypto_twin_health' has no attribute 'bc'` with the wiring removed,
> `stash pop` restored cleanly, re-verified 34/34 green in `test_crypto_twin_health.py` (0.23s,
> confirming zero accidental real network calls leaked into the mocked tests). Broader sweep
> `test_crypto_twin_health.py` + `test_broker_canary.py` -> **72/72 PASS**. Cross-checked
> `test_preopen_readiness.py`'s 1 pre-existing failure (`test_fetch_eod_flatten_reality_reads_real_tmp_files`,
> `KeyError: 'Gamma_EodFlatten'`) is unrelated and pre-existing -- reproduces identically with
> both my files stashed out, confirmed before closing this item as clean. Curated safety gate
> (31+5-suite) PASS. **Rail-4 (PAPER/visibility-only, guard test + revert path + this REVOKE
> report):** touches `setup/scripts/crypto_twin_health.py` (additive: 1 new import, 1 new
> try/except block in `main()`, 1 new key in the printed JSON) + `backtest/tests/
> test_crypto_twin_health.py` (2 new tests). Zero `params.json`/`heartbeat_core.py`/
> `filters.py`/placement/exit code touched -- this is observability, not a capital decision;
> the canary can never place an order or change any trading behavior. **Revert:**
> `git revert 3332454` (2 files, clean no-behavior-change rollback -- the twin's tick and
> `preopen_readiness.py`'s existing fail-open handling of a stale canary file are both
> unaffected either way). Cost: ~$2.6 (STAGE 0/1 reads incl. engine-health/STATUS/queue/
> self-audit/fill-funnel/task_scorer, module read, wiring-site survey, edit, 2 new tests,
> 2 RED-proof round trips via git stash, 1 broader regression sweep, 1 curated safety gate
> run, 1 commit, this queue/STATUS update).

### Recovered audit-tail findings (G10, 2026-07-08 â€” not yet fixed)
- [ ] F23-F27-JOURNAL-CALENDAR (MED) :: manual trades not journaled to trades.csv (F23 â€” still open for MANUAL/core trades; FLEET fills CLOSED 2026-07-09 via fleet_journal_bridge commit 59f176f + firm-brief hook); macro/news calendar stale (F27 â€” **RESOLVED 2026-07-09**: deterministic macro_calendar.py + Gamma_MacroCalendar 07:45 ET registered; root cause = weekly-review section-8a never reached + Scout budget-capped since 06-22; commit 410360a). :: status:F23-remainder-only
- [x] PDT-WIRE-FLEET-ARMS (MED, risk-gate, doctrine-gap) :: fleet arms (safe-1/safe-3/risky-1/risky-3) log `day_trades: 0` and never call `pdt_tracker` -- core (safe/bold) enforces Rule 7 for real via `pdt_tracker.fetch_day_trades_used_5d`, fleet does not. Paper doesn't enforce PDT so no live-money exposure yet, but this MUST close before any fleet arm is armed live (OP-0 #1 precondition). Documented HANDOFF-2026-07-09-TRUTH-AND-EXITS T4 + markdown/0dte/risk-rules.md. Do NOT wire now -- would silence the only fleet arms feeding the WS2 exit-parity study. :: depends:WS2-exit-parity-study-complete :: status:todo
  **CLOSED (superseded) 04:57 ET 2026-09-03 (Fable):** the premise ('MUST close before any fleet arm is armed live') rested on the $25K PDT floor, repealed 2026-06-04 and verified on both accounts; the PDT counterfactual (09-02) returned FAIL_PDT_STAYS_AS_IS, i.e. the self-imposed day-trade accounting is not demonstrably costly; Saturday's Rule-7 rewrite records that fleet day-trade counting stays as-is with `fleet_pdt_enforce` deliberately OFF; and tonight's rule-audit R7 pass found Alpaca exposes no `daytrade_count` / `pattern_day_trader` field to wire against. What survives is the OBSERVATION the auditor now records per arm. If a fleet arm is ever armed live, the live-arming checklist (OP-0 #1) carries 'day-trade awareness observation present', not a PDT gate. :: status:superseded

### TRADE-TO-LEARN-CUMULATIVE-DIGEST (MED, visibility, spun off F3 close 2026-07-18)

### TASK-SCORER-MULTILINE-STATUS-READ (LOW, hygiene, found+fixed 2026-07-22 conductor AFTERHOURS)

### TASK-SCORER-STATUS-VOCAB-GAP (LOW, hygiene, found during F3 close 2026-07-18)

### Tier 0.1 â€” 2026-07-01 pipeline-audit fix-order (FUNCTION FIRST â€” J ratified FULL PAPER AUTONOMY 2026-07-01)

> Merged from the interactive TaskList + `markdown/audits/PIPELINE-AUDIT-2026-07-01.md` (audit finding #5: "the conductor reads only queue.md â†’ the autonomy loop literally cannot see the plan"). Trading-path edits for PAPER accounts are now sanctioned per the 2026-07-01 grant â€” each ships with a guard test that REDs on regression + a git-revert path + a REVOKE report.

- [ ] PARAMS-DEAD-KNOB-DISPOSITION (MED, engine-correctness) :: Drain the 24-key KNOWN_DEAD allowlist in `test_params_consumer_reconciliation.py` â€” for each dead knob decide RESTORE (wire a real consumer) or REMOVE (delete the key + its _doc). Buckets: session-timing (6, scheduler-hardcoded), ~~resilience-harness (4, _shared.ps1 literals)~~ **CLOSED slice 1**, exit-flags (2), macro-bias-v2 (4, never wired), liquidity-gate (5, order path prose-approximate), catalyst/journaling flags (2), sizing scale-up (1). Each disposition is a small rail-4 change; the shrinks-only ratchet auto-verifies. Ref markdown/audits/PIPELINE-AUDIT-2026-07-01.md break #7. **SLICE 1 DONE 2026-07-19 (conductor, commit pending) â€” resilience-harness bucket (4/24), REMAINING 20/24 across 5 buckets.** Disposition: `max_consecutive_failed_mcp_calls` / `max_consecutive_tv_failures_before_kill_switch` / `wedged_state_alert_hours` **REMOVE** â€” verified zero consumers ANYWHERE in the repo (the params.json doc's "also embedded in _shared.ps1" claim was false; `run-tv-watchdog.ps1`'s live self-heal design relaunches immediately + always-alerts on every relaunch, it never built a consecutive-failure counter). `min_disk_free_mb` **RESTORE** â€” `Test-DiskSpaceAvailable` now reads it live via a new `Get-ParamsMinDiskFreeMb` helper in `_shared.ps1` (fail-open to 100 on read/parse error), replacing the hardcoded `-MinFreeMB 100` at its one call site. **Bonus fix while restoring:** the reconciliation guard's OWN consumer-corpus glob never scanned `setup/scripts/*.ps1` (only top-level `setup/*.ps1` installers) nor `automation/state/fleet/*.py` (the live fleet-lane consumer) â€” both added; the 2nd gap was independently false-flagging `recency_min_size_enabled` dead for 4+ days (tracked since 2026-07-15 per STATUS.md history), now fixed as a side effect. New guard `backtest/tests/test_params_dead_knob_disposition_2026_07_19.py` (8 tests, incl. 3 live `powershell.exe` subprocess round-trips proving the restore is a real live read + fail-open). RED-proofed via `git stash`. Curated safety gate (31+5) PASS + `test-self-heal.ps1` 23/23 PASS (zero regression on the pre-existing disk-space test). Next slice should take session-timing (6 keys) or exit-flags (2 keys) â€” both similarly bounded. :: depends:none :: status:pending-slice1-of-6-done
- [ ] SINGLE-STRATEGY-REGISTRY-DESIGN (HIGH, engine-architecture) :: Collapse the 3 disjoint hardcoded strategy menus (engine_cli literals / setup_dispatch 5-tuple / fleet 2-entry REGISTRY) into ONE registry so adding a validated family stops requiring hand-edits in 3 places; must cover the order-placement + exit wiring surface so a registered setup can actually fill. Audit: "no automated path from analysis/recommendations/ into any of them." Ref markdown/audits/PIPELINE-AUDIT-2026-07-01.md. **SLICE 1 DONE 2026-07-18 (conductor) -- the setup_dispatch<->validator seam, the seam that has ACTUALLY caused 3 live incidents (F26-DISPATCH-191-FAILED-GREEN x2 + this session's 120-consecutive-cron-failure level_break_first_strike RED), is now structurally drift-proof.** Corrected re-trace of the item's own premise first: `engine_cli.py` does NOT hold a 3rd hardcoded strategy menu (grepped -- only one incidental setup-name string at L472, unrelated to the extra-setups plugin architecture); the real 3 surfaces are (a) `setup_dispatch.py`'s `SetupDispatcher.run()` dispatcher list [the live "extra setups" plugin registry], (b) `crypto/validators/v53_setup_dispatch.py`'s hand-typed `_KNOWN_SETUP_NAMES` mirror [the repeat-offender], (c) `automation/state/fleet/strategies.py`'s 2-entry fleet `REGISTRY` [a genuinely separate concern -- fleet-arm strategy selection, not extra-setup dispatch; NOT touched this slice]. Fixed (a)+(b): hoisted the inline `dispatchers` list in `setup_dispatch.py` to a module-level `DISPATCH_ROSTER` constant (method referenced by NAME so a validator can import safely) + a derived `KNOWN_SETUP_NAMES` frozenset; `v53_setup_dispatch.py` now IMPORTS `KNOWN_SETUP_NAMES` instead of hand-typing a mirror set -- there is no second copy left anywhere to drift. Also fixed `pipeline_promoter.read_dispatcher_roster()`'s regex (it parsed the OLD inline-tuple shape; updated to match the new `DISPATCH_ROSTER` row shape, still source-text-parsed not imported, preserving its documented backtest-venv-free + always-reflects-on-disk-file properties). Guards: `test_graduated_guards.py::test_setup_dispatch_names_registry_sync` rewritten (was AST-parsing `run()`'s method body -- fragile, broke the moment `run()` became a comprehension; now a direct identity/derivation check) + new `backtest/tests/test_setup_dispatch.py::TestDispatchRosterSingleSource` (5 tests: roster<->run() parity, KNOWN_SETUP_NAMES derivation, validator import-not-hand-type source-level proof, every roster method resolvable). RED-proofed live via `git stash`/`git checkout stash@{0} -- <files>` round-trip (stash-pop collided with concurrent-fire state-file writes -- recovered cleanly via targeted `git checkout` from the stash, no work lost). Verified: gym 104/104 GREEN, 40/40 targeted pytest (`test_setup_dispatch.py`+`test_pipeline_promoter_contract.py`+`test_graduated_guards.py -k setup_dispatch`), 84/84 broader money-path/armability/trade-to-learn suites, zero regressions. **Confirmed pre-existing, NOT caused by this slice** (identical failures with changes stashed out): `test_no_new_dead_params_knob` + `test_watcher_registry.py` (a `bollinger_squeeze_watcher.py` file exists on disk unregistered -- separate gap, unrelated surface). **REMAINING for a future slice:** the fleet `strategies.py` REGISTRY unification + the order-placement/exit-wiring automation the item's full scope asks for -- that is materially larger/riskier (crosses into live order-placement code across a 3rd system) and was deliberately NOT attempted in this one bounded fire; left `[ ]` open, not closed, so it stays visible for a dedicated future fire. :: depends:none :: status:slice1-done-setup_dispatch-validator-seam-drift-proofed-remainder-open
- [ ] CLAUDE-PROFITLOCK-DOCTRINE-RECONCILE (LOW, doctrine-hygiene, **propose-only â€” CLAUDE.md**) :: Doctrine drift surfaced by ADJUDICATE-CD-2026-06-29-001: CLAUDE.md:28 describes "chandelier **trailing** profit-lock (arms at +5% favor, trails 15% off HWM)" but the validated (pk-2026-06-28-001 OOS all-pass) AND live-core value is `profit_lock_mode="fixed"`. Verify whether the doctrine's "chandelier trailing" wording refers to a SEPARATE arming mechanism vs the profit_lock_mode knob; if genuinely drifted, propose a one-line CLAUDE.md reconciliation to J (rail-4 propose-only). Not urgent (near-inert). :: depends:none :: status:pending
- [ ] RECONCILE-GUARD-READ-TO-MUTATE-BLIND-SPOT (LOW, engine-correctness, follow-up to tonight's 95a603b reconciliation guard) :: `v15_profit_lock_mode` PASSES the params-consumer reconciliation guard because `promote_keeper.py` reads it (L130) â€” but that is a READ-TO-MUTATE consumer (reads current value only to decide whether to rewrite it), NOT a behavior-path consumer; the live exit path (heartbeat_core) ignores the key entirely (forces "fixed"). So the presence guard's "has a reader" check counts a mutate-only reader as a live consumer â†’ a behaviorally-dead knob evades the ratchet. Consider a stricter behavior-consumer classification (exclude promote_keeper/actuator writers from the "consumer" set) OR document the class in the guard. Lesson-inbox: `2026-07-02-read-to-mutate-consumer-masks-dead-knob.md`. Rail-4 CLEAR. :: depends:none :: status:pending
> **CLOSED 2026-07-21 ~09:xx ET (conductor, AFTERHOURS), commit `f60da48`.** Found a THIRD
> incompatible resolution mechanism while fixing this (not just the two the item named):
> `_set_status`'s for-loop-with-break is ALSO first-wins but via a different code shape than
> `revert`'s `next()` scan. Shipped one shared `resolve_proposal(pid, rows)` + `DuplicateProposalError`
> in `setup/scripts/autonomy_actuator.py`, routed into all three call sites
> (`sync_companion_approvals` / `_set_status` / `revert`). Semantics match
> `test_proposal_id_uniqueness.py`'s existing ACTIVE_STATUSES exactly (pinned by a same-file
> test): a terminal+active duplicate (harmless `promote_keeper` re-emission) now resolves to the
> ACTIONABLE row regardless of file order -- the old first-wins scans could have silently
> mutated a terminal sibling instead; two ACTIVE rows sharing an id raises loud;
> `sync_companion_approvals` catches the exception per-decision (logs `duplicate_id_blocked`,
> skips only that id) so one collision can't stall the rest of a companion-approval batch.
> **Verified this fire:** `backtest/tests/test_resolve_proposal.py` (10 new tests) RED-proofed
> via `git stash` on `autonomy_actuator.py` alone -- 9/10 failed against the pre-fix module with
> the exact expected `AttributeError` (no `resolve_proposal`/`DuplicateProposalError` yet),
> `git stash pop` restored cleanly, re-verified 44/44 green across the full actuator test family
> (`test_resolve_proposal` + `test_autonomy_actuator` + `test_proposal_id_uniqueness` +
> `test_autonomy_auto_approve` + `test_actuator_recency_gate`). Curated safety gate (31+5) PASS
> (ran automatically via the pre-commit hook). `git ls-tree HEAD` confirms all 3 files landed
> on HEAD, not just staged. L207 updated with the SHIPPED note (no longer "owed"). **Rail-4
> CLEAR** as the item itself flagged -- zero params/heartbeat_core/filters/placement/exit files
> touched; `autonomy_actuator.py` only ever edits those files THROUGH its own gated
> `apply_ops`+safety-gate+snapshot path, never directly. **Revert:** `git revert f60da48`
> (3 files, additive + one lesson-doc edit).
### Tier 0.5 â€” drain the live self-check BROKEN flags (rig-never-traded audit fix-order)

- [ ] LEVELS-UPSTREAM-DEDUP-SOURCE (LOW, producer-hygiene, follow-up to LEVELS-CONTRADICTORY-ROLES-DRAIN) :: `refresh_levels_intraday` now self-heals the 6-9x curated PMH/PML duplication every run, but a non-duplicating SOURCE is cleaner. Find the upstream producer appending duplicate curated `PMH_/PML_` entries (candidates: `automation/scripts/compute_levels.py`, `setup/scripts/fetch_swarm_data.py`, or the premarket draw) and dedup at the source. Rail-4 CLEAR (producer code). NOT urgent (downstream normalization covers it). :: depends:none :: status:pending

### Tier 0 â€” regime-appropriate edge (STANDING DIRECTION: climb off the dead premium axis)

- [~] CLIMB-LADDER-NEXT-RUNG-IS-CLASS (HIGH, engine-edge R&D) :: **'instrument' rung CLOSED 2026-06-28 conductor (commit 04adc35).** The range-scalp FADE lens (`LEVEL_REJECT_LIVE`) was tested on deep-data MES/MNQ futures (N=379/259, escaping the 25-day OPRA wall that blocks the SPY range-scalp at n=8) via `backtest/autoresearch/futures_range_fade_probe.py` â†’ **RANGE_FADE_DOES_NOT_GENERALIZE**: both instruments WALK_FORWARD_FAIL_REGIME_FLIP (IS-negative 2025 â†’ only positive in 2026 OOS, concentrated top3 101%/193%, long-direction artifact). Combined with the 2026-06-20 control (momentum fleet dead), the 'instrument' rung is now dry for BOTH lenses. Backlog item 7a + golden guard `test_futures_range_fade_probe.py` (6/6). **NEXT RUNG = 'class' (a different signal INPUT):** named live candidate is **Tier-1.5 W2 â€” GEX zero-gamma-flip-distance + net-GEX-sign as a continuation/abstain regime FILTER on the live edge** (dealer-positioning input class, genuinely NOT a re-skin of the ~64 dead price-signal families; unlock = a cheap forward OI-fetch). First bounded slice = assess FREE OI-data availability (verify-now, same discipline that confirmed the cached futures bars this fire), then build the GEX filter probe if data exists; else the honest conclusion is the 0DTE-SPY frontier is data-gated until a new feed appears (W-REJECTED). Rail-4 CLEAR (research). **DATA-AVAILABILITY RESOLVED 2026-06-29 conductor (commit 69cd429):** the free OI data EXISTS and is ALREADY being banked daily â€” `backtest/tools/cboe_oi_bank.py` (free CBOE CDN, native gamma+OI, $0) + `automation/scripts/gex_capture.py` (Alpaca N=2) accrue to `journal/gex-archive/`; `gex_regime.py` already computes the full dealer-GEX tag (net-GEX sign / zero-gamma flip / walls). VERIFIED LIVE: `Gamma_CboeOiBank` Ready, NextRun 06-29 15:55 ET, accrued 06-22..06-26 (5 trading days). **So the 'class' rung is NOT "no data" data-gated â€” it is CALENDAR-TIME-gated:** a GEX backtest needs ~60-90 as-of days (per `gex_regime.assess_backtest_feasibility`); we have ~5. Shipped a C7 continuity guard (`backtest/tools/gex_archive_health.py` + `test_gex_archive_continuity.py` 12/12, live verdict GREEN) so the months-long accrual can't die silently. **CONTINUITY NOW VISIBLE 2026-06-29 conductor (commit e99aa45):** the OPTIONAL LOW follow-up is DONE (stronger than the daily-brief version) â€” `check_gex_archive` wired into the every-minute engine-health beacon (`setup/scripts/engine_health.py`), NON-CRITICAL (never trade-halts / never REDs the critical verdict), surfaces the GREEN/YELLOW/RED continuity verdict in `engine-health.json` every 1min AND pings J once on a genuine multi-day stall via the transition-only alerter. Guard `test_engine_health_gex_archive.py` (7/7, bite-tested the non-critical invariant). The silent-accrual-death loop is CLOSED â€” the checker the 01:54 fire built now actually RUNS against the live archive on a schedule. **NEXT (no build owed until ~60-90 days accrue):** the GEX-filter probe waits on calendar time; nothing more to wire. The standing direction now needs a genuinely-NEW unblocked needle-mover beyond GEX-accrual-wait â€” OR accept the 0DTE-SPY frontier is calendar-gated on GEX (premium axis dead L182-184; instrument rung closed; range-scalp data-blocked n=8). :: depends:none :: status:class-rung-data-engine-alive+guarded+VISIBLE-calendar-time-gated

### Tier 1 â€” engine correctness / loose ends from tonight (CONTEXT-106..109)

> The 3 BP-* loose ends are CLOSED (2026-06-19) â€” see `## Completed`. STAIRSTEP-REDESIGN remains the one open Tier-1 item (genuine eval-first redesign, not a quick fix).

> **END-TO-END WIRE-UP gaps (added 2026-06-26, blueprint `markdown/planning/PROJECT-END-TO-END-WIRED-2026-06-26.md`).** This pass FIXED the two P0s: G1 (engine PLACE_FAIL â€” `run-heartbeat-core.ps1` now sets `GAMMA_CORE_ARMED=1`+`GAMMA_CORE_MANAGES_EXITS=1`, guarded) and G2 (systemic DST ET-clock â€” `setup/scripts/et_clock.py` + 9 live-path migrations + 3 task re-registers, guarded). The remaining P1/P2 below are the wiring gaps that keep the loop from closing on itself unattended. The ONE non-code blocker is G3 (J must arm + send `ship <id>`).

- [~] G4-EXEC-WIRE-EXTRA-SETUPS (P1, engine-wiring) :: **WIRING SHIPPED DISARMED 2026-06-27 conductor (commit d1d775c).** `run_account()` now routes fired `dispatch_extra_setups` signals through the SAME `_execute` path (flat-verify + quality-lock + risk_gate + free-model veto) on a non-ENTER ribbon tick, via `_route_extra_setups`/`_synthetic_verdict_from_extra`/`_extra_exec_armed` (direction long->ENTER_BULL / short->ENTER_BEAR). **SAFE BY DEFAULT â€” the dead-knob is now wired but exec stays OFF:** gated on a NEW params key `extra_setup_exec_armed[setup]=True`, DISTINCT from the detector-enable flags (`j_vwap_cont_enabled`/`gap_and_go_enabled` already true). Key absent in BOTH params files -> byte-identical no-op (every fired row logs WATCH_NOT_ARMED, `_execute` never called; verified). Graduated to a 24-test guard `backtest/tests/test_g4_extra_setup_routing.py` that REDs if exec-arm ever defaults on or gates on the detector-enable (kills L47/L70/C11/C14 reintroduction). 57 existing core/dispatch tests still green; curated safety gate PASS. **REMAINING (each a separate fire):** (a) **ARM** `vwap_continuation` (and/or others) â€” set `extra_setup_exec_armed.vwap_continuation=true` in `automation/state/params.json` â€” is RAIL-4 J-gated AND recency-gated: the combined book is recency-RED (DIRECTION-BLOCK-BATCH-RECONCILE Tier-2); license_monitor pings J on RED->green, arm then. Do NOT auto-arm. (b) a watcher-signal PARITY test (backtest vs the new live-verdict surface) before arming â€” the 24-test guard pins the routing CONTRACT but not signal-vs-backtest parity. (c) `prior_rth_close` into `_build_payload` for gap_and_go (the dispatch currently reads it from today-bias.json; payload plumbing is a gap_and_go-arming prereq only). :: depends:none :: status:wiring-done-arm-is-j-gated
- [ ] G13b-VETO-NAIVE-TS-HARDEN (LOW, engine-defensive, follow-up to G13) :: Defense-in-depth (NOT urgent â€” production feeds tz-aware ISO so this never triggers today): in `engine_cli._classify_sameday_5m`, localize a parsed *naive* `timestamp_iso` to America/New_York before constructing `crypto.lib.bar.Bar` (which raises ValueError on a naive open_time â†’ currently swallowed â†’ 'unknown' â†’ silent veto-disable). Changes veto behavior ONLY on the naive-caller path (production unaffected â€” localize is a no-op for already-tz-aware ts), so it makes a fired veto MORE likely (safe direction) but is still a live-behavior touch â†’ validate no-regression vs the anchor days (5/04 must stay RANGE=no-veto) before ship. The characterization test `test_naive_timestamps_silently_fail_open_is_characterized` must be updated deliberately when this lands (turns a silent regression into an intentional decision). :: depends:none :: status:pending
- [ ] G15-REVIEWER-GLOB-OP20 (P2, research-kitchen) :: kitchen_reviewer globs only `*chef-nemo*.md` â†’ Chef-authored date-prefixed candidates (e.g. structure-veto) are NEVER auto-reviewed; AND nearly all PROMOTE verdicts route to `_LEADERBOARD-pending.md` because free-model cooks rarely contain all 6 OP-20 keywords â†’ human-Claude is the mandatory final curator. FIX: expand the reviewer glob to also match `strategy/candidates/[0-9]*.md` newer than the review window; lower the auto-promote bar to 4-of-6 OP-20 disclosures (flag the missing 2 in the row instead of blocking). Both are kitchen_reviewer.py edits, not loop-breaks. :: depends:none :: status:pending
- [ ] G3-AUTONOMY-APPLY-LOOP-NEVER-FIRED (P0-but-J-gated, autonomy) :: The approveâ†’applyâ†’commitâ†’learn HALF of the autonomy loop has NEVER fired â€” conductor-approvals.jsonl + autonomy-changelog.jsonl DO NOT EXIST (verified), all 17 conductor-proposals.jsonl rows are status=pending. Gamma_AutoApply + Gamma_DiscordResponder ARE firing (LastResult=0) but are INERT because J has never replied `ship <id>`. findâ†’propose works; apply is dead-code-in-practice. NOT a code break. RESOLUTION: (a) J sends `ship <id>` on Discord for the pending non-doctrine proposals, OR (b) the conductor bundles the 17 pending into ONE explicit Discord call-to-action ping. The 14 CLAUDE.md doc-fold proposals (rail-4) need an interactive lesson-author/J session â€” one batch CLAUDE.md edit drains all 26 L169-L187 index folds (see CLAUDE-INDEX-FOLD-BATCH above). This is the single biggest still-needs-J item to close the loop. :: depends:none :: status:awaiting-j-action
- [~] OPEN-BLINDNESS-TV-HANG (DOWNGRADED HIGHâ†’LOW, **ROOT CAUSE LARGELY MOOT 2026-06-27 conductor â€” stale breadcrumb L181/L185**) :: **The TV-CDP-hang root cause was ELIMINATED by the 2026-06-25 LLM-heartbeat retirement.** Verified live: `Gamma_Heartbeat`/`_Aggressive` (the LLM TV-reading path with the 280s tree-kill in run-heartbeat.ps1) are **Disabled**; the live engine is `Gamma_HeartbeatCore` = `setup/scripts/heartbeat_core.py`, which reads **NO TradingView / no MCP / no CDP** (docstring line 10) â€” SPY 5m + ribbon via direct Alpaca REST, VIX via yfinance, broker via REST. A TV chart reload at the bell can no longer hang a live tick (the live engine never reads TV). **The never-blind concern MOVED onto those direct network reads, and they are ALL already bounded** (verified 2026-06-27): `_fetch_spy_5m` `timeout=15` (the critical price+ribbon path), both broker `urlopen` `timeout=10`, and the 3 `yf.download` VIX calls now carry an EXPLICIT `timeout=10` (were relying on yfinance's default which DIFFERS across the two installed pythons 0.2.66 vs 1.0 â†’ made explicit, zero behavior change). **GRADUATED to a permanent guard** `backtest/tests/test_heartbeat_core_sight_timeouts.py` (4 tests, bite-tested non-vacuous) â€” a static AST assertion that EVERY `urlopen`/`yf.download` in the live engine passes a bounded positive `timeout=` literal, so a future refactor can't silently re-introduce an indefinite-hang (urlopen default `timeout=None` = block forever; a hang is not an exception â†’ the fail-open except never fires). **DEAD-PATH RESIDUAL (LOW, only if the LLM heartbeat is ever re-enabled):** the original STEP-(b) fast-fail TV timeout + STEP-(c) Safe/Bold stagger + 97.8KB heartbeat.md trim all apply to the now-Disabled LLM path â€” not a live blocker. **DECOUPLED the 3 dependents (RANGE-SCALP / RIBBON-LAG / POSITION-MONITOR): `depends:` updated â€” the live-engine sight is hang-resistant, so the "sight first" precondition is satisfied.** ~~ORIGINAL ITEM (historical):~~ **LIVE PROOF 2026-06-24** â€” engine went BLIND through the 09:30â€“09:40 PMH-rejection scalp (SPY 737.13â†’735.47, J called it manually). Root cause: TV chart reloaded at the bell (symbol flipped `BATS:SPYâ†’AMEX:SPY`, "chart still loading"); the 09:35 tick (only tick live during the rejection) HUNG on TV reads and got tree-killed at the 280s timeout (`run-heartbeat.ps1` line 164) with ZERO output; first completed read was 09:40 â€” after the move. The `TV_DATA_LIVE` fail-closed gate (heartbeat.md line 131) only catches stale-but-RETURNING data, NOT a TV call that HANGS. **Alpaca bars (`mcp__alpaca__get_stock_bars`) were live the entire time.** **LAYER-1a COMPUTE CORE SHIPPED 2026-06-24 (commit 178b6b7):** `backtest/lib/ribbon_fallback.py` â€” source-agnostic `compute_ribbon(closes)` â†’ price + Saty ribbon stack (BULL/BEAR/MIXED/UNKNOWN) + spread_cents, fail-closed on short input, 11/11 tests incl. a byte-identical EMA PARITY guard vs `compute_ema_snapshot.py`. **STEP-1 stale-note CORRECTED:** the EMA spec is NOT off-repo â€” it is canonically fingerprinted in `backtest/lib/ribbon_config.json` (fast=13/pivot=20/slow=48/sma=50, all within 5c of live TV, 2026-05-07) and reused by construction (resolves C11/L180, no live TV re-read needed). **STEP-(a) ALREADY DONE â€” breadcrumb reconciled 2026-06-24 conductor 22:00:** the Alpaca-barsâ†’ribbon wiring is LIVE in BOTH heartbeats. `automation/prompts/heartbeat.md` lines 132-137 (+ `aggressive/heartbeat.md`) define the TV FALLBACK: on a TV error/stale, fetch `mcp__alpaca__get_stock_bars` â†’ run `python automation/scripts/ribbon_cli.py '<closes_json>'` â†’ exit 0 = use stack/price/ema_*/spread_cents (data_source=alpaca_fallback, TV_FALLBACK_ACTIVE), exit 1 = SKIP_TV_DATA_STALE. `ribbon_cli.py` exists + behaves per contract; it was UNTRACKED (L164) + had no contract test â†’ TRACKED + graduated to `backtest/tests/test_ribbon_cli_contract.py` (10/10, commit d90d9da) so a RibbonRead-field rename or a clean-checkout drop can no longer silently re-blind the engine. REMAINING (rail-4 propose-only, swap at CLOSE): (b) fast-fail TV reads (cap ~15s + 1 retry, no burn to 280s â€” this is the part that actually saves the 09:35 tick; the fallback only fires AFTER a TV read returns/errors, so a 280s HANG still tree-kills before the fallback runs â€” the fast-fail timeout is the true unlock, NOT the fallback compute); (c) stagger Safe vs Bold off each other (LOCK_BUSY collision at 09:36). Also folds the QUEUED-but-unbeaten "trim 97.8KB heartbeat.md + stagger" item (memory `project_engine_self_healer`). **Build+test against replay; swap at CLOSE (not mid-session â€” a regression in the 97KB prompt/wrapper during RTH blinds it worse). Live for next open.** NOTE: Layer-1 alone would NOT have captured this trade â€” see RIBBON-LAG item. :: depends:none :: status:pending
### QQQ-DIVERGENCE-REALFILLS-REPLAY (MED, research, filed 2026-07-22 ~evening ET, chef, next-step of QQQ-DIVERGENCE-CONFLUENCE-BACKTEST)

- [ ] QQQ-DIVERGENCE-REALFILLS-REPLAY (MED, dedicated chef fire, real-fills replay) :: The
  QQQ divergence/confluence first-pass proxy test (`QQQ_AGREEMENT_INFORMATIVE`, spread
  +0.96 SPY-pts aligned) had one open confound per its own disclosure #3: does the
  reclaimed-vs-none spread survive controlling for realized volatility at entry, or is it
  a trend-day/volatility-regime proxy in disguise? **RUN 2026-07-22 (conductor,
  AFTERHOURS, acting as chef):** `confound_check_by_volatility()` added to
  `backtest/tools/qqq_divergence_confluence_study.py` â€” splits the population at median
  realized SPY volatility (own trailing 20-bar, no-look-ahead), recomputes the spread
  within each half. **Result: `SPREAD_SURVIVES_VOL_CONTROL`** â€” low-vol half spread
  +0.826 (n_reclaimed=8/n_none=108), high-vol half spread +1.132 (n_reclaimed=13/n_none=94)
  â€” both positive, similar magnitude, if anything slightly LARGER in the high-vol half
  (opposite of what a pure volatility-proxy artifact predicts). Confidence raised 6/10 â†’
  7/10 (per-half n_reclaimed is thin, 8 and 13, below the usual n>=10 floor per stratum â€”
  only the pooled n=21 clears it; a median split is a coarse control, not a continuous
  regression). Full addendum: `strategy/candidates/2026-07-21-205400-qqq-divergence-
  confluence-first-pass.md`. **NEXT STEP (this item, not yet executed â€” a genuinely
  heavier task with its own budget):** fund the full real-fills replay â€” reuse
  `ribbon_ride_strike_exit_ab.py`'s per-strike SS-B replay machinery (~250 signals Ã—
  per-strike OPRA option-chain fetch/replay), stratified by `qqq_label` (join on
  `entry_ts`, both already cached in `analysis/recommendations/qqq-divergence-
  confluence-study.json`). Only if that clears the standard OP-11/OP-16 bar (OOS positive
  AND WF>=0.70 AND sub_window_stable AND anchor_no_regression) does a wiring proposal (a
  scored `breadth_agreement` composite feature, never a hard block per C20/C22) reach
  `conductor-proposals.jsonl`. :: depends:none :: status:pending

- [~] BOLD-FLEET-PRODUCER-KEYSTONE (HIGH, engine-architecture) :: **PRODUCER-VS-BACKTEST PARITY GATE GRADUATED TO CI 2026-06-28 conductor (commit fdafb28).** The 36s standalone `backtest/replay_fleet_arms.py` (per-arm entry-fidelity: signal-driven plan_entry vs run_backtest GT) was rotting outside CI -> a regression breaking producer<->backtest fidelity (or a loose arm starting to OVER-trade) would ship green. Extracted `compute_arm_fidelity()` (compute vs print split) + added `backtest/tests/test_replay_fleet_arms.py` (6 tests, FULL-suite/CI only â€” ~36s, NOT the curated <2s pre-commit gate, same category as test_graduated_guards). Invariants: extra==0 for EVERY arm (safety-critical over-trade direction), score parity >=95%, no silent replay errors, + a shrinks-only missed-ratchet. **REAL FINDING the run surfaced: 3 of 4 arms entry-faithful (safe-1/safe-3/risky-1: extra=0/missed=0, ARM-READY on entry timing) but risky-3 (LOOSEST bold arm, min_triggers=1) is NOT â€” MISSES 2 GT trades (bars 1394, 1540; extra=0) = a producer-vs-backtest under-trade divergence that BLOCKS arming risky-3.** Both halves of G4's parity-before-arming prereq now CI-asserted (consumer=test_fleet_keystone_consumer d52e737; producer-vs-backtest=this). **NEXT bounded parity slice NAMED: diagnose risky-3's 2 missed â€” bars 1380->1394 and 1540->1548 are dedup-adjacent, so verify whether `_entry_fidelity.blocked_pre` over-blocks a fresh GT entry (artifact -> fix comparison + tighten ratchet to 0) vs a true `plan_entry` under-fire on min_triggers=1 (real arming blocker).** :: **CONSUMER-LINK GUARD SHIPPED 2026-06-28 conductor (commit d52e737).** The producer guard (test_fleet_producer_keystone, 12 tests) proves `build()` EMITS `signal['bold'].passed=true`, but never exercised the live CONSUMER â€” the bold fleet only TRADES that signal if `fleet_executor.plan_entry` turns the bold block into an ENTER for a loose arm, and that link had NO fast guard (only the heavy standalone `replay_fleet_arms.py` covered it â†’ a regression leaving the fleet inert AT THE CONSUMER would ship green). NEW `backtest/tests/test_fleet_keystone_consumer.py` (5 tests, offline/$0) closes the producerâ†’consumer link: synthetic gated-A+ BOLD core row â†’ real `build()` â†’ real `plan_entry`; loose arm (risky-3) ENTERs 'C' qty8, tight arm (risky-1, require_confluence) HOLDs on a NON-elite A+ (selectivity bites) but ENTERs on an elite one, a SAFE arm reads `signal['safe']` production-faithful HOLD (perception-confound fix proven at the consumer), + a BITE (scoring_peak=False â†’ loose arm HOLDs = chain reverts INERT). Arms SYNTHETIC (not live accounts.json) so the guard survives slice-4's re-tier. This is the CONSUMER half of G4's "parity-before-arming" prereq; the producer-vs-backtest half remains `replay_fleet_arms.py` â€” still a standalone script NOT in the curated suite, so **graduating replay_fleet_arms.py to a fast pytest is the next bounded parity slice.** **FIRST SLICE SHIPPED + A CONFIRMED MONDAY-OPEN TIMEBOMB FIXED 2026-06-28 conductor (commit c8f2465).** Per L181/L185 verified the breadcrumb FIRST -> SUBSTANTIALLY STALE: the keystone scoring-peak derivation is ALREADY LIVE (`SCORING_PEAK_LIVE=True` flipped 2026-06-25, `USE_CORE_LEDGER=True`, `EMIT_STRATEGIES=True`); `build()` emits dual-perception `signal['bold']` off the BOLD core ledger via `_bold_passed_blocks`, so a gated-but-A+ DOES emit `passed=true` for the loose arms (the inverse of the original inert-fleet bug â€” the "passed only from production action off the SAFE ledger" critique no longer describes the default). GRADUATED that contract to a guard `backtest/tests/test_fleet_producer_keystone.py` (12 tests, bite-tested): looser-than-production property, the score-without-entry-trigger quality gate, the asymmetric thresholds (bull 9/11, bear 8/10), the ENTRY_TRIGGERS allowlist, the end-to-end dual-perception reproduction (gated 11/11 -> `bold.bull.passed=True` while top-level stays production-faithful False), + a BITE test proving `SCORING_PEAK_LIVE=False` reverts the fleet to INERT (so a silent revert can't return). WHILE BUILDING IT the producer's exact production call CRASHED -> uncovered + FIXED the et_clock aware-ET_TZ utcoffset recursion (see ET-CLOCK-RECURSION-FIXED below) that would have frozen shared-signal.json on Mon 06-29 open. **REMAINING (the real multi-fire build â€” each slice CHANGES live fleet behavior, so each needs WATCH-validate + after-close deploy): (2)** real per-arm sizing override in `fleet_executor._params_for` (position_sizing_tiers/strike, NOT the dead min_contracts knob C14); **(3)** fix the equity==2000.00 boundary qty inversion; **(4)** accounts.json re-tier + resolve the perception-source confound; **(5)** wire `select_exit_params`/`select_strike_offset` into `fleet_live._place_live` (hardcodes -50% + generic v15 strike). ORIGINAL (historical, much now stale): **2026-06-24 â€” 7-agent workflow w2dnmn1pr designed 3 looseness tiers; the adversarial VERIFY phase KILLED the naive design (verdicts: loose=unsafe, medium=needs_adjustment, tight=sound) and surfaced the REAL bug, deeper than gates.** KEYSTONE: `automation/state/fleet/build_shared_signal.py` derives `bull/bear.passed` ONLY from production `action=='ENTER_*'` (L85-88) AND reads the SAFE ledger `automation/state/decisions.jsonl` (L31). So when the SAFE heartbeat HOLDs (gated â€” as it did ALL of 2026-06-24), the shared signal emits `passed=false` on every tick â†’ **EVERY fleet arm is inert; the fleet can only make arms TIGHTER than production, NEVER looser.** This is the exact inverse of J's "3 bold accounts take a gated-but-perfect signal 3 ways." Confirmed live: shared-signal.json @09:55 shows bull.passed=false score=7; risky-1/decisions.jsonl has 0 ENTER rows ever. **The fleet runs `fleet_live.py --quiet --live` (run-fleet-executor.ps1 L44, Gamma_FleetExecutor scheduled) â€” safe-3 + risky-1 are live:true â†’ LIVE-but-INERT (placing nothing because the producer never emits passed).** SECONDARY verified findings: (a) the proposed `params_patch` min_contracts=3 lever is FICTION (0 repo hits; qty comes from position_sizing_tiers not min_contracts â†’ min_contracts never binds at this equity; C14 dead-knob); (b) equity==2000.00 lands in the [2000,10000) OTM-2/qty-8 tier (boundary inversion) â†’ over-sized AND RISK_CAP-blocked; (c) gate_override only honors {min_confidence,min_triggers,require_confluence_or_sequence,min_setup_quality=='EXCELLENT'} â€” all ADD selectivity, and min_confidence/min_setup_quality DENY-on-missing on the confidence-less signal (would make a "loose" arm the TIGHTEST); (d) perception-source confound: fleet_rest arms = SAFE-derived, bold-2 = BOLD-derived â†’ can't attribute a delta to looseness alone; (e) fleet_live._place_live hardcodes stop=-50% + generic v15 strike (WP-0/WP-5 per-setup dispatch NOT wired). **REAL FIX SEQUENCE (gated on verification, deploy after-close NOT mid-session â€” fleet is live):** (1) KEYSTONE: rewrite build_shared_signal to (i) read the BOLD ledger for bold arms (or emit per-account blocks), (ii) derive passed from SCORING-PEAK + real trigger (`score>=thresh AND entry-trigger present`) so a gated 11/11 emits passed=true, (iii) populate triggers_fired(multi)+confluence+est_premium; WATCH-validate it reproduces today's 11:00 bull=11 as passed=true BEFORE any live behavior change. (2) real per-arm sizing override in fleet_executor._params_for targeting position_sizing_tiers/strike, not min_contracts; +parity test (C14). (3) fix equity-boundary qty. (4) THEN accounts.json re-tier (risky-3â†’loose drop structure_override+live:true; risky-1â†’medium drop PUT_ONLY) + resolve perception confound. (5) wire select_exit_params/select_strike_offset into _place_live. Full design+verdicts: task w2dnmn1pr output. :: depends:none :: status:pending
- [ ] STAIRSTEP-REDESIGN (MED) :: STAIRSTEP_CONTINUATION eval-first redesign â€” currently RETIRED 2026-06-18 (anti-J-edge; detector returns None, v45 gym PASS confirms 0 post-retirement fires). Any future promotion needs eval-first / J redesign: (1) docstring + v45 gym fixture used FABRICATED bar values (not the real 5/07 tape); (2) 5/07 is a J LOSS day; every tested logic fix worsened edge_capture. :: depends:none :: status:pending

### Tier 2 â€” J-ratification proposals (DRAFT, awaiting J ruling per Rule 9)

> These are NOT blocked-on-J foot-guns â€” they are genuine Rule-9 doctrine changes that need J's explicit call. Surface in the next brief; do not auto-ship.

- [ ] J-RULING-BOLD-STRIKE-OFFSET (MED, Rule-9) :: Bold strike offset: `aggressive/params.json#strike_offset_itm: 2` matches Safe's; `run_dual_account.py` docstring claims Safe=ATM/Bold=ITM-2. Likely stale docstring (per-tier selection happens in heartbeat) â€” verify intended. (CONTEXT-107 Q2.) :: depends:none :: status:awaiting-j-ratification
- [ ] HEARTBEAT-SPY-LOGGING-CLARIFICATION (LOW, Rule-9) :: heartbeat.md output format says `spy={x}` without defining whether x is `Latest.close` (v15.1 closed-bar result) or the live quote. In practice Claude logs the live/in-progress price â†’ ~$0.50-$1.50 false divergence on HOLD ticks â†’ audit false positives. Fix: add note `spy=Latest.close (NEVER in-progress bar / quote_get live price)`. Zero trading-logic change. :: depends:none :: status:awaiting-j-ratification
- [ ] MM-05-WAKE-FIRE-REVIVAL (HIGH, Rule-9) :: Wake fires were paused (burned Max-plan quota). With MiniMax in place they can resume cheap. Option A (hybrid: Claude orchestrates, MiniMax generates content, ~$0.20-0.40/fire) recommended over Option B (pure-MiniMax, ~$0.05-0.15/fire, medium risk). Full proposal in archive. :: depends:none :: status:awaiting-j-ratification
- [ ] MM-06-INTRADAY-SWARM (MED, Rule-9) :: Add `Gamma_SwarmIntraday` 12:00 ET re-run of swarm Stages 2-4 for a mid-session bias sanity check (~$0.07/fire, ~$1.50/mo). Requires OP-28 amendment (intraday swarm currently undefined). :: depends:none :: status:awaiting-j-ratification
- [ ] MM-07-VALIDATOR-MULTI-PASS (LOW, Rule-9) :: 3-pass swarm validator (technical / macro / level contrarian) instead of 1-pass devil's-advocate. ~$0.007/fire. :: depends:none :: status:awaiting-j-ratification
- [ ] DIRECTION-BLOCK-BATCH-RECONCILE (HIGH, Rule-9) :: **PRE-SHIP CHECK DONE 2026-06-26 conductor (analysis/self-audit/PRE-SHIP-CHECK-direction-block-2026-06-26.md).** The STATUS [2026-06-26 ~11:50 ET] STAGED batch landed PARTIAL, not as one atomic commit. (1) **HOLD #2/#4** â€” `j_vwap_reclaim_fb_enabled` + `j_vix_dayside_enabled` must stay dormant: individually YELLOW but the combined Safe-2 ATM book is recency-RED (n=17, -$8.01/tr clear) + Bold ATM book RED (n=10, -$60.12/tr); the recency-confirmation gate (2026-06-22) forbids a live flip into RED. license_monitor pings J on RED->green => enable then. This is the CORRECT held state â€” do NOT auto-flip. (2) **J-DECISION: `gap_and_go_enabled=True`** went live with NO recency-tracker basis (WATCH->LIVE candidate) â€” confirm A/B-validated, else propose revert-to-dormant. **PARTIALLY ANSWERED 2026-07-16 evening** (redesign ship-list arming attempt, see `GAP-AND-GO-REVALIDATION-BEFORE-ARM` below): NOT confirmable as A/B-validated on the live path as currently wired (06-28 re-check found 0 robust cells; no isolated exit override exists, so an armed fill would trade under ribbon_ride's SS-B shape, not its validated chart-stop-only cell). Detection stays enabled (WATCH, zero behavior change); exec-arm stays absent pending the revalidation spec'd below â€” this is NOT yet the "propose revert-to-dormant" branch since `gap_and_go_enabled` (detection) was never the thing in question, only exec-arming was. (3) **J-DECISION: finish-or-drop** the un-applied tail â€” `entry_bar_body_pct_min` 0.20 (staged->0.0), `aggressive/params.json#require_bearish_fill_bar` true (staged->false), `block_conf_lvl_rec_afternoon` true (staged->false). Rail-4: conductor cannot apply; needs J ruling. :: depends:none :: status:awaiting-j-ratification
- [ ] GAP-AND-GO-REVALIDATION-BEFORE-ARM (MED, filed 2026-07-16 evening, worker-tier) :: gap_and_go PUT arming attempt REFUSED (validity check failed â€” full trace: `automation/overnight/STATUS.md` [2026-07-16 ~evening ET] entry + `markdown/research/SIX-ACCOUNT-DAILY-HYPOTHESIS-REDESIGN-2026-07-16.md` Â§7). Two blockers: (A) the 2026-06-19 ratification's PUT-side edge (+$67.96/tr) collapsed ~7x (+$9.66/tr, top5_day_pct=556%) on a 2026-06-28 re-validation over a near-identical window â€” never reconciled beyond "different window," and is the codebase's own already-standing reason it's excluded (`SIGNAL-SHAPE-COVERAGE-2026-07-10.md`). (B) `heartbeat_core.py`'s `_SETUP_EXIT_OVERRIDES` (line 1181) has no `gap_and_go` entry â€” an armed fill would silently trade the ribbon_ride SS-B structure-stop shape (cat-cap -50%/TP1 ~+50-100%), not its validated CHART-STOP-ONLY/TP1+30%/runner-2.5x cell (identical bug class to the pre-2026-07-02 vwap_continuation bug). **BLOCKER B CLOSED 2026-07-18 conductor-weekend.** Shipped: `_SETUP_EXIT_OVERRIDES["gap_and_go"]` (isolated `j_gap_and_go_premium_stop_pct=-0.50` / `j_gap_and_go_tp1_pct=0.30` in `automation/state/params.json`, mirroring go_live_params) + a new generic `stop_mode` (literal, not a params-key) support in the `_xov`-shape builder + `_synthetic_verdict_from_extra` now threads `row["stop_price"]` (the watcher's own first-bar-extreme, already stamped by `setup_dispatch.dispatch_extra_setups`) through as `verdict["rejection_level"]` â€” the exact input `exit_manager.ExitState.from_entry`'s structure-stop resolution needs. Verified inert for every OTHER armed/isolated setup (vwap_continuation etc. â€” none declare `stop_mode`, so they stay byte-identical "premium"). 9 new guards (`test_gap_and_go_exit_wiring_2026_07_18.py`) + RED-proofed (git-stash both edited files -> exact expected `KeyError`s) + 178/178 broader G4/money-path/trade-to-learn/exit-manager/exit-actuator suites green, zero regressions. **gap_and_go's exec-arm stays ABSENT (still WATCH-only) â€” this fixes the shape, it is NOT an arming decision.** **BLOCKER A STILL OPEN** (unchanged scope, genuinely separate/larger research fire): re-run the edgehunt sweep on the full window through today with a proper walk-forward split to reconcile the 06-19-vs-06-28 disagreement before any arming attempt. **Falsification rail (apply once armed, per redesign Â§6):** gap_and_go live-fills check at n>=15 â€” WR materially below 72.6% or negative expectancy -> pull the flag (`extra_setup_exec_armed.gap_and_go: false`, single-key revert). :: depends:none :: status:blocker-B-closed-blocker-A-open

### Tier 3 â€” research items not owned by the cook-queue loop

- [ ] RIBBON-SPREAD-PER-TIER-DESIGN (MED) :: `ribbon_min_spread_cents=30` applies globally to ALL quality tiers (LEVEL/ELITE/SUPER). Hypothesis: ELITE/SUPER setups tolerate a tighter spread. Design a per-tier spread table + backtest. (Also in cook-queue, source=claude.) :: depends:none :: status:pending
- [ ] SAFE-MULTIDAY-APPROACH-GATE (MED) :: When price within $0.30-0.50 of a multi_day level (PDH/PDL/weekly), trigger on APPROACH rather than exact touch. (Also in cook-queue, gamma-autonomous.) :: depends:none :: status:pending
- [ ] FALSE-BREAK-OPEN-CARRY-GATE (LOW, defensive) :: Do-no-harm gate protecting the LIVE bearish_rejection edge: suspend bear entries 30 min after a â˜…â˜…â˜… named level (Carry/Active/multi-day) is breached at the 09:35 open bar AND the next closed bar recovers above it (single-bar L59 floor_hold variant, n_min=1). NOT entry-hunting (so not OP-22-superseded) but single-day evidence (one -$204 trade 2026-05-21) + C28/L156 diminishing-returns on bear-rejection exit refinement. Full spec preserved in `strategy/candidates/_chef-inbox/2026-05-21-false-break-open-carry-gate.md.DONE`. Promote to chef fire ONLY IF (a) >=3 more days show the same false-break-open->bear-trap pattern, or (b) J prioritizes bear-rejection exit hardening. :: depends:none :: status:pending

### Tier 4 â€” long-standing low-priority carry-overs (verify still relevant before picking up)

- [ ] T60 (LOW) :: TradingView MCP J-drawn-line capture â†’ key-levels.json (`j_drawn` source, tier=Active). :: status:pending
- [ ] T101 (MED) :: Capture â‰¥5 TV MCP fixtures at different bar-cycle phases for `crypto/data/fixtures/` (v13_tv_mcp_parity test cases). :: status:pending
- [ ] T102 (MED) :: Investigate v02 source-parity drift (~23% iterations disagree >0.05% Coinbase vs yfinance). Deeper diagnostic: log WHICH bar disagreed; consider Alpaca crypto as 3rd source for 2-of-3 voting. :: status:pending
- [~] EOD-PHASE-2.2/2.3/2.4 (MED, weekend) :: **NARROWED 2026-07-18 (conductor).** Traced against current reality before picking up: 2.2 (tight fingerprint matching) and 2.3 (hit-rate+expectancy via OPRA fills / simulator_real) were ALREADY fully real in `modules/forensics.py` (590 lines, built 2026-06-15) â€” the item's own description was stale. Of 2.4's "9 stub modules", only 2 were actually still Phase-1-shallow at this fire's start (`analyze_execution`, `analyze_doctrine`) â€” `detection`/`macro`/`technical`/`watcher_fleet`/`lessons`/`risk`/`process`/`tomorrow`/`engine_health` were already real. **Shipped this fire: `analyze_execution` real impl** â€” `modules/execution.py` (new): fill-timing-vs-trigger-bar (matches ENGINE_ENTER decision time_et to first entry-fill time_et, degrades gracefully to neutral-low when no decisions.jsonl match exists rather than crashing â€” verified live via a real CSV-fallback smoke run on 2026-07-17 where engine_decisions was genuinely empty), partial-fill detection (multi-clip entry + spread-secs), slippage (kept from Phase 1). Wired into `main.py` replacing the `stubs_mod.analyze_execution` call. 6 new guard tests (`test_eod_deep_execution_phase24.py`) + 17/17 green with the existing detection-phase3 suite; live smoke run on 2026-07-17 confirms end-to-end (`phase: "2.4"`, real per-trade evidence, score 77/100, no crash). **Remaining real scope, narrowed to ONE item:** `analyze_doctrine` (currently only checks `rule_breaks_today` count â€” Phase 2 should score PER-TRADE doctrine compliance dimensions, not just a flat rule-break tally). Left open, correctly scoped now (was 9 modules, is 1). :: depends:none :: status:pending
- [ ] SHOT-DISCORD-ALERT (LOW) :: Wire shotgun-scalper stage5 completion into `discord-watcher.py` (pattern from `check_v15_appeared()`). :: status:pending
- [ ] T24 / T25 / T16 / T17 / T106 / T107 (LOW) :: Misc one-shots: mtf_confluence spec (T24), grinder-concurrency-audit (T25), refactor sniper_evaluator (T16), verify today-bias schema (T17), full-history in-progress-leak replay (T106), per-tick chart_read replay forensic tool (T107). Verify relevance before starting â€” several predate the 05-23 reset. :: status:pending

### OPTION-CACHE-ITM-COVERAGE-GAP (LOW, spec-only, adjacent finding, filed 2026-08-02 from OPTION-BAR-RESOLUTION-BIAS-2026-08-02)

## Blocked
(none active â€” Rule-9 J-ruling items live in Active Tier 2, which are decisions not blocks)

## Forward backlog (deliberate-future)
See automation/overnight/forward-backlog-2026-06-19.md for the post-all-night-loop forward work (Tier 0 BEARISH_REJECTION exit/regime; Tier 1 decision-lib P3/P4; Tier 2 key-levels archive + watcher RETIRE).

## HARVESTED-FROM-GYM (auto-queued by crypto/benchmarks/gym_harvester.py)

- [ ] HARVEST-REGIMEEXT-20260903-100018 (LOW) :: v09_regime TREND_UP dominant: 56/80 bars (70%) | last_regime=TREND_UP atr_14=122 — sustained BTC trend; check SPY correlation :: key=EDGE_REGIME_EXTREME:2026-09-03T07:00:00+00:00:TREND_UP :: depends:none :: status:queued
- [ ] HARVEST-SWEEP-20260903-100019 (MED) :: v14_sweep liquidity-grab at level=77000 dir=down bar_idx=93 | wick_excess=0.0918% close_back=0.1066% — feeds v15.2 sweep-blocker doctrine :: key=EDGE_SWEEP_DETECTED:2026-09-03T09:57:01.913129+00:00:77000:down:93 :: depends:none :: status:queued
- [ ] HARVEST-SWEEP-20260903-100020 (MED) :: v14_sweep liquidity-grab at level=78000 dir=up bar_idx=173 | wick_excess=0.0491% close_back=0.1730% — feeds v15.2 sweep-blocker doctrine :: key=EDGE_SWEEP_DETECTED:2026-09-03T09:57:01.913129+00:00:78000:up:173 :: depends:none :: status:queued
- [ ] HARVEST-SWEEP-20260903-100021 (MED) :: v14_sweep liquidity-grab at level=78000 dir=up bar_idx=178 | wick_excess=0.0480% close_back=0.1340% — feeds v15.2 sweep-blocker doctrine :: key=EDGE_SWEEP_DETECTED:2026-09-03T09:57:01.913129+00:00:78000:up:178 :: depends:none :: status:queued
- [ ] HARVEST-RSIEXTREME-20260902-100018 (MED) :: BTC v03_indicators rsi_14=18.72 (oversold) at last_close=76993.02 bin=2026-09-02T08:45:00+00:00 :: key=EDGE_RSI_EXTREME:2026-09-02T08:45:00+00:00:oversold :: depends:none :: status:queued
- [ ] HARVEST-RSIEXTREME-20260902-100019 (MED) :: BTC v03_indicators rsi_14=15.00 (oversold) at last_close=76832.01 bin=2026-09-02T08:50:00+00:00 :: key=EDGE_RSI_EXTREME:2026-09-02T08:50:00+00:00:oversold :: depends:none :: status:queued
- [ ] HARVEST-RSIEXTREME-20260902-100020 (MED) :: BTC v03_indicators rsi_14=13.42 (oversold) at last_close=76744.59 bin=2026-09-02T08:55:00+00:00 :: key=EDGE_RSI_EXTREME:2026-09-02T08:55:00+00:00:oversold :: depends:none :: status:queued
- [ ] HARVEST-RSIEXTREME-20260902-100021 (MED) :: BTC v03_indicators rsi_14=18.12 (oversold) at last_close=76800.71 bin=2026-09-02T09:00:00+00:00 :: key=EDGE_RSI_EXTREME:2026-09-02T09:00:00+00:00:oversold :: depends:none :: status:queued
- [ ] HARVEST-RIBBONFLIP-20260902-100022 (MED) :: v08_ribbon flip MIXED -> BEAR | spread=446.41>100 | recent dist BULL=62 BEAR=51 MIXED=87 :: key=EDGE_RIBBON_FLIP:2026-09-02T09:00:00+00:00:BEAR :: depends:none :: status:queued
- [ ] HARVEST-SWEEP-20260902-100023 (MED) :: v14_sweep liquidity-grab at level=77000 dir=down bar_idx=63 | wick_excess=0.0202% close_back=0.0538% — feeds v15.2 sweep-blocker doctrine :: key=EDGE_SWEEP_DETECTED:2026-09-02T09:57:01.875204+00:00:77000:down:63 :: depends:none :: status:queued
- [ ] HARVEST-SWEEP-20260902-100024 (MED) :: v14_sweep liquidity-grab at level=77000 dir=up bar_idx=105 | wick_excess=0.0116% close_back=0.0711% — feeds v15.2 sweep-blocker doctrine :: key=EDGE_SWEEP_DETECTED:2026-09-02T09:57:01.875204+00:00:77000:up:105 :: depends:none :: status:queued
- [ ] HARVEST-SWEEP-20260902-100025 (MED) :: v14_sweep liquidity-grab at level=77000 dir=up bar_idx=189 | wick_excess=0.0173% close_back=0.0672% — feeds v15.2 sweep-blocker doctrine :: key=EDGE_SWEEP_DETECTED:2026-09-02T09:57:01.875204+00:00:77000:up:189 :: depends:none :: status:queued
- [ ] HARVEST-RSIEXTREME-20260901-100018 (MED) :: BTC v03_indicators rsi_14=17.24 (oversold) at last_close=77941.57 bin=2026-09-01T08:30:00+00:00 :: key=EDGE_RSI_EXTREME:2026-09-01T08:30:00+00:00:oversold :: depends:none :: status:queued
- [ ] HARVEST-RSIEXTREME-20260901-100019 (MED) :: BTC v03_indicators rsi_14=15.67 (oversold) at last_close=77842.97 bin=2026-09-01T08:35:00+00:00 :: key=EDGE_RSI_EXTREME:2026-09-01T08:35:00+00:00:oversold :: depends:none :: status:queued
- [ ] HARVEST-RIBBONFLIP-20260901-100020 (MED) :: v08_ribbon flip MIXED -> BEAR | spread=370.03>100 | recent dist BULL=38 BEAR=77 MIXED=85 :: key=EDGE_RIBBON_FLIP:2026-09-01T09:00:00+00:00:BEAR :: depends:none :: status:queued

### T-GYM-20260619 HIGH gym-session RED for 2026-06-19

**Audits failing:**
- chart-data-verify (RED): 0 bars checked, max div $0.0000
- heartbeat-tick-audit (MISSING): tick-audit output not found
- watcher-state-inspector (MISSING): watcher-state output not found

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260619 HIGH gym-session RED for 2026-06-19

**Audits failing:**
- chart-data-verify (RED): 0 bars checked, max div $0.0000
- heartbeat-tick-audit (MISSING): tick-audit output not found
- heartbeat-pulse-check (RED): max gap 15.02min
- watcher-state-inspector (RED): could-not-load-bars-for-date

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260623 HIGH gym-session RED for 2026-06-23

**Audits failing:**
- heartbeat-tick-audit (MISSING): tick-audit output not found
- watcher-state-inspector (MISSING): watcher-state output not found

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260624 HIGH gym-session RED for 2026-06-24

**Audits failing:**
- heartbeat-tick-audit (RED): 78 live ticks, 4 MISALIGNED-CRITICAL (5.1%)

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

- [ ] ENGINE-VECTORIZATION (HIGH, perf â€” the "thousands fast" unlock) :: **2026-06-24: the backtest is 54s/combo â†’ grinds take hours; profile shows the cost is per-bar pandas row-indexing (1.6M `.iloc`/`fast_xs` calls), NOT cacheable I/O.** Baseline for byte-identical validation captured: `backtest/autoresearch/_vectorize_baseline.json` (strike_offset=2/L2/-8% â†’ n=159, sum_pnl=2593.09, **hash c9b7c82bce74250d** â€” NOTE: this exact combo now reproduces n=308/total=$3982.94 on today's larger OPRA window, per the LAYER-1 fire below; n/sum_pnl in this stale baseline reflect the 2026-06-24 data cutoff, not a regression). THREE hot layers (each validated against the hash after change, 54-80s/run): (1) **levels.py `_detect_from_history`** â€” `history=spy_df.iloc[:bar_idx+1].copy()` + re-derive date/time on the GROWING slice every day (365Ã— = O(nÂ²), ~44s cumulative). spy_df_full ALREADY carries `date`; precompute `time`+tz once, skip the per-day copy/derive (~1.8Ã— alone, most isolated â†’ DO FIRST). **[LAYER 1 SHIPPED 2026-07-23, see note below â€” honest result was ~6%, not 1.8Ã—; the boolean-mask slice construction dominates that layer, unaddressed.]** (2) **filters.py per-bar lookback loops** â€” `prior_bars.iloc[j]["close"]` double-index in range loops (L393/408 sweep, +`.iloc[k]` at L377/452/521/650/1000/1187) â†’ precompute close/high/low/open/vol numpy arrays ONCE in run_backtest, inject via BarContext (new fields), replace .iloc with array[k]. THIS is the big multiplier â€” cProfile (2026-07-23) confirms: `fast_xs`/`_ixs`/`__getitem__` chain totals ~110s cumulative of a ~205s profiled run (profiler overhead inflates absolute seconds; relative share is the signal), concentrated in `filters.py:evaluate_bullish_setup`/`evaluate_bearish_setup` (~90s+40s cumulative) and `engine/score.py:score_bar` (~65s). **NEXT STEP, not yet attempted.** (3) **orchestrator bar loop** L865 `bar=spy_df.iloc[idx]` + L906 `vix_aligned.iloc[idx]` per bar â†’ array access. Target: 54s â†’ ~3-5s (10-15Ã—) so the 3360 grid runs in ~minutes. Do as a DEDICATED build, one layer at a time, hash-validated. :: depends:none :: status:layer1-shipped-layer2-3-open

> **LAYER 1 SHIPPED 2026-07-23 ~17:12-18:10 ET (conductor, AFTERHOURS), commit `2c6eaf75`.**
> `_detect_from_history` now skips re-deriving "date"/"time" via `.dt.date`/`.dt.time` when the
> caller already supplies those columns (mirrors the pre-existing `_find_swept_levels` precedent
> in the same file); `orchestrator.py` precomputes "time" on `spy_df_full` once up front
> alongside the already-precomputed "date" so its hot path (`_level_per_day` cache-miss, once
> per trading day) benefits automatically.
>
> **Verified byte-identical (OP-33, not just "should work"):** ran the full real-OPRA-fills
> reproducer (`strategy_space_grind --cell OTM-2:L2:pct_-8`) before AND after the change â€”
> n=308, total=$3982.94, edge_capture=$1100.97, wf=2.762, wr=0.1786, max_dd=-$988.33 identical
> to the last decimal both times. 3 new guard tests
> (`test_levels_precomputed_columns_parity.py`: skip-if-present==recompute parity,
> date-only-precomputed still derives time independently, no-precompute path unaffected) +
> 23/23 pre-existing `test_level_quality_guards.py` + 31+5 curated safety gate all PASS.
> Post-commit `git show 2c6eaf75 --stat --name-status` confirms exactly the 3 intended files
> landed.
>
> **Reported honestly, not oversold (no-oversell doctrine):** cProfile'd the same cell and
> isolated `_detect_from_history` in a direct microbenchmark (365 calls, real data, no
> cProfile overhead skewing the number): 27.33s â†’ 25.74s, a genuine but modest ~6% win at this
> layer â€” NOT the item's speculated "~1.8Ã— alone." Root cause of the shortfall: the dominant
> remaining cost inside this layer is the boolean-mask slice construction
> (`spy_df_full[spy_df_full["timestamp_et"] <= bar_time]`, O(n) per day, unchanged by this fix),
> not the `.dt.date`/`.dt.time` derivation this fix targeted. Full wall-clock A/B on the whole
> grind cell (83.4s â†’ 87.2s) showed NO measurable difference â€” within run-to-run noise, because
> this layer is a small fraction of total runtime once real-OPRA-fills I/O and layer-2's ~1.6M
> `.iloc` calls dominate (cProfile breakdown filed above in the item body).
>
> **Scope + revert:** pure `backtest/lib/` perf + a new test file â€” zero params/heartbeat_core/
> filters/placement/exit/CLAUDE.md touched. Revert: `git revert 2c6eaf75`.
>
> **NEXT (not this fire):** layer 2 (filters.py's `.iloc`-per-bar lookback loops, the real
> "big multiplier" per the cProfile numbers above) is the next dedicated build â€” precompute
> close/high/low/open/vol as numpy arrays once in `run_backtest`, inject via `BarContext`,
> replace `.iloc[k]` with `array[k]` at the ~7 cited call sites. Item stays open (HIGH), not
> closed â€” layer 1 of 3 done, honestly quantified, 2 remain.

- [ ] GATE-TIERS-IMPLEMENT (HIGH, fleet-architecture) :: Implement the per-arm gate-tier design from markdown/audits/GATE-PROVENANCE-AUDIT-2026-07-02.md: SAFE=full stack / BASE=untouched / RISKY=safety-class-only + min_triggers 1, via gate_profile+gate_params in fleet accounts.json gate_override (absent = byte-identical today), per-arm _HARD_SKIP_VERDICTS; guards per step, single-key revertible; measure per-arm fill-funnel N=10 days. J directive 2026-07-02 ("risky account should take the one-gate-away trade"). :: depends:none :: status:rank3-shipped-ranks1-4-open

> **RANK #3 SHIPPED 2026-07-23 ~21:12-21:45 ET (conductor, AFTERHOURS), commit `ecde12f8`.**
> Audit section 4's per-arm hard-skip design: `_HARD_SKIP_VERDICTS` (require_bearish_fill_bar's
> global block) was baked into the shared signal's "bold" perception block at BUILD time --
> every non-safe arm (bold-2 control, risky-1 tight, risky-3 loose) inherited the identical
> hard-skip regardless of gate tier, so "risky arm takes the one-gate-away trade" was
> structurally impossible for THIS gate specifically (rank #3 in the audit's ranked list).
> `build_shared_signal.py` now exposes `score_peak_passed`/`hard_skip_action` alongside the
> UNCHANGED `passed` field; `fleet_executor._effective_passed()` lets an arm opt out per-verdict
> via `accounts.json gate_params.hard_skip_verdicts` (absent key = byte-identical today).
> risky-3 (the only LIVE RISKY-tier arm -- safe-1's loose cell retired 2026-07-11) wired with
> an empty list, so it now rescues a setup ONLY require_bearish_fill_bar blocked, while
> bold-2/risky-1 still honor it (fill-bar stays validated OOS +$1,153/WF 18.5 on Bold control).
> **Verified:** 6 new guard tests (byte-identical default path + rescue path + still-honors-
> named-verdict + unaffected-when-no-hard-skip-fired + end-to-end via `_chosen_side`) +
> 283/283 fleet tests + participation-cascade/probe-arm/plan-all/six-account-routing suites
> green + curated safety gate PASS. Post-commit `git show ecde12f8 --stat --name-status`
> confirmed exactly the 4 intended files landed.
> **NOT done this fire (ranks #1/#4/#2-partial remain open, item stays HIGH):** rank #1
> (block_elite_bull relax-for-RISKY -- the #1 blocker, ~4.2 eps/wk) and rank #4 (doji-gate
> relax-for-RISKY) both need the SAME `gate_params` mechanism extended to cohort/score-side
> gates (currently only the hard-skip axis is wired); ranks #2/#5 (G8 momentum bug, E5
> confidence gate) were ALREADY closed by earlier fires (2026-07-11) before this one started.
> Per-arm fill-funnel measurement (N=10 days) not yet run -- needs live days to accrue first.
> Revert: delete accounts.json's risky-3 `gate_params`/`gate_params_doc` keys (byte-identical),
> or `git revert ecde12f8`.
### T-GYM-20260702 HIGH gym-session RED for 2026-07-02

**Audits failing:**
- crypto-gym (53 validators) (RED): 102/104 pass (KNOWN_FLAKY excluded: 1)

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260703 HIGH gym-session RED for 2026-07-03

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass
- chart-data-verify (RED): 0 bars checked, max div $0.0000
- heartbeat-tick-audit (MISSING): tick-audit output not found
- watcher-state-inspector (MISSING): watcher-state output not found

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260706 HIGH gym-session RED for 2026-07-06

**Audits failing:**
- crypto-gym (53 validators) (RED): 102/104 pass (KNOWN_FLAKY excluded: 1)

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-ENGINE-LAG-20260707 HIGH heartbeat_core lagging -- missed J-called BEARISH_REJECTION entry (09:50 close < 749.28)

**Symptom:** 2026-07-07 ~09:50-10:00 ET SPY rejected the ~750 ribbon, CLOSED 749.03 below 749.28 support (5m), ran to 748.7. Engine held every tick (verdict HOLD, bear_score 4 / bull_score 7) and MISSED the entry J called live. Gamma placed manual paper puts instead (Safe 5x747P @0.82 ord eb818929, Bold 3x750P @2.14 ord b858f462).

**Two root causes -- diagnosed live from core-decisions.jsonl, NOT yet fixed (market-hours engine edit forbidden -- scar):**
1. STALE PRICE FEED: decisions at 09:53-09:54 showed spy=749.655 (the 09:45 5m close) while real spot was 748.87 -- engine price input lags ~2 bars / ~8 min, so it literally cannot see the dump in time. Find where heartbeat_core sources spy (beacon eye / ema-snapshot?) and why it lags the live tape; the static ema-snapshot.json was also stale (yesterday EOD compute).
2. LAGGING htf_15m GATE: htf_15m=BULL (slow 15m EMA still elevated from yesterday 752 rally) capped bear_score at 4 even as the 15m ROLLED OVER (lower highs 752.4->750.94->750.18, gap-down, broke session support). C28 lagging-ribbon class -- the htf classifier must weight recent 15m structure/BOS, not just a slow EMA stack.

**Action (AFTER-HOURS only):** reproduce both from automation/state/core-decisions.jsonl (07-07 rows); (a) fix price-feed freshness + add a guard that REDs if engine spy diverges > ~15c from the live beacon; (b) make htf_15m responsive to 15m rollover/BOS + guard that a confirmed support-break-close registers as bear. Validate on the 07-07 tape via the override harness, ship with guard+revert per paper-autonomy rail. :: status:pending

**REFINEMENT (2026-07-07 ~10:07 ET, read the actual code + J scalp spec):**
- CORRECTED bug #1: not a stale beacon -- heartbeat_core._fetch_spy_5m (L637) decides on CLOSED 5m bars and drops the forming bar (_htf_15m_stack(df.iloc[:-1]) L468, no-look-ahead C6). So best-case entry is the 09:50 support-break CLOSE (~748.6), ~$2 later than J's rejection entry. FIX: make BEARISH_REJECTION_RIDE_THE_RIBBON fire on the REJECTION CANDLE (wick off ribbon/round-level + rollover / lower-high), not only on the confirmed support-break close. Must NOT break C6 -- validate it is not look-ahead (rejection candle is CLOSED before entry).
- bug #2 confirmed in code: _htf_15m_stack (L321) needs 50x 15m bars (48-EMA warmup) so at the open it runs on PRIOR-DAY 15m bars -> stale BULL -> caps bear_score. FIX: de-weight the slow 15m EMA stack when the intraday 15m has a fresh rollover/BOS; or gate on recent-structure not just EMA stack.
- J SCALP PROFILE (certified scalp move, encode as the exit/size profile for this setup): size 3-5 contracts; QUICK profits (take MOST off fast at TP1); HOLD 1-2 runners. Distinct from v15 tp1_qty_fraction 0.8 -- this is take-most-quick + tiny-runner.
- SHIP: AFTER-HOURS ONLY. Validate the earlier-trigger vs J real trades (OP-16 edge_capture -- must not degrade the winners or add the losers) BEFORE apply. guard+revert per paper-autonomy rail. NOT a mid-session hot-patch (rule 9 + market-hours-edit scar).

**CORRECTION supersedes the above (2026-07-07 ~11:05 ET, /think-like-fable, primary evidence):**
The earlier 'stale price feed + de-lag htf_15m' framing was WRONG. Root cause from engine_cli.py:446-462 + today core-decisions:
- Routing = side.PASSED (threshold) + len(triggers_fired), NOT raw bear/bull score. Bear NEVER passed today: 0 triggers fired the whole move (setup=None every tick). bull_score 8-10 vs bear 4-7 is a red herring.
- Core bear setup needs level_rejection/sequence_rejection = price approach-and-reject an ACTIVE level. Today was an OPENING-DRIVE rejection off 750.93, but 750.93 only became a level AFTER the 09:30 bar set the high; price never re-tested it. Core engine has NO ribbon-wick trigger.
- J's EXACT setup already exists: backtest/lib/watchers/ribbon_rejection_wick_detector.py (spec = J's 2026-07-02 live read, identical to today). It is UNWIRED because it was VALIDATED AND KILLED: battery 2025-01..2026-07 OPRA real fills, 0/24 BH-FDR survivors, J-exact config N=174 WR 65.5% but expectancy -16.16/tr, OOS -30, both dirs negative. C3 premium-bleed / inverted R:R (chandelier cuts winners, -30% stops bleed losers). Scorecard analysis/recommendations/ribbon-rejection-wick.json.

**REVISED ACTION (after-hours, offline, on fresh OPRA -- NOT the old de-lag plan):**
1. RE-VALIDATE the wick detector with J's ACTUAL SCALP EXIT (the disclosed-untested lever): quick TP ~+30-40%% or at next level + FAST structure stop (level reclaim) + 1-2 runners, vs the battery's fixed TP+50/stop-30/chandelier which the kill nail blames. Full 18mo, OOS split, BH-FDR, drop-top3, slippage-to-breakeven. Wire as ENTRY only if it survives ALL. CAVEAT L58: this R:R family historically does NOT rescue via exit knobs -> treat as ~low-P.
2. Wire ribbon_rejection_wick as a VETO/exit signal regardless (scorecard's own future_vein): bear wick => do-not-enter-bull + tighten runners. Today the engine nearly took a BULL reclaim at 09:34, 2 min before the dump. Low-risk, likely-positive.
3. MINOR hygiene: prune expired levels from key-levels.json (731.22 exp 06-30, 734.52 exp 06-29 still present in a 07-07 feed) -- did NOT cause today.
DO NOT wire on today's n=1 win. :: status:pending

### T-WICK-EXITGRID-20260707 HIGH RUN AFTER CLOSE -- exit-redesign re-validation of J's ribbon-rejection scalp

**Built 2026-07-07 (/think-like-fable), import-clean + all 8 exit configs construct. UNVALIDATED vs data until the smoke runs.**
Premise: ribbon_rejection_wick entry FAILED 0/24 with a FIXED exit; the kill nail blamed the exit; J's SCALP exit (quick TP + tight stop + partial+runner) is the one un-searched lever. This battery grids ONLY the exit (8 pre-registered configs, entry fixed to J-anchor), BH-FDR across the 8, full robustness bar.
**Runbook (after close, reaper-exempt venv, ONE process -- NEVER mid-session):**
  1. SMOKE first (proves harness + knob non-vacuity): === RIBBON_REJECTION_WICK exit-grid battery [SMOKE] ===
master: 2274 RTH bars 2026-05-19 09:30:00..2026-07-01 15:55:00
[1/3] superset scan
  scan 0/1865 bars  events=0  0s
  scan done: 1865 bars -> 321 superset events (1s)
  321 superset events
[2/3] knob non-vacuity self-check
  [knob-check] baseline slice pnl=294  fast_tight slice pnl=163  LIVE (differs)
[3/3] exit-grid battery
  E1_baseline_repro  N=  15 WR=0.47 exp=$ -67.68 OOS_exp=$ -67.68 drop3=$ -1386.6 p=0.962 (1s)
  E2_quick_scalp     N=  16 WR=0.38 exp=$ -44.27 OOS_exp=$ -44.27 drop3=$ -1017.0 p=0.954 (2s)
  E3_quick_runner    N=  16 WR=0.44 exp=$ -18.49 OOS_exp=$ -18.49 drop3=$  -702.6 p=0.521 (2s)
  E4_mid_runner      N=  16 WR=0.44 exp=$ -16.88 OOS_exp=$ -16.88 drop3=$  -702.6 p=0.468 (3s)
  E5_tight_stop      N=  17 WR=0.18 exp=$ -37.85 OOS_exp=$ -37.85 drop3=$ -1044.0 p=0.823 (3s)
  E6_fast_tight      N=  17 WR=0.35 exp=$ -17.96 OOS_exp=$ -17.96 drop3=$  -660.6 p=0.646 (4s)
  E7_bigtp_tight     N=  17 WR=0.35 exp=$ -30.04 OOS_exp=$ -30.04 drop3=$  -866.0 p=0.846 (4s)
  E8_j_scalp         N=  16 WR=0.44 exp=$  -8.08 OOS_exp=$  -8.08 drop3=$  -561.9 p=0.351 (5s)

VERDICT: FAIL (survivors 0/8) -> C:\Users\jackw\Desktop"nalysis
ecommendations
ibbon-rejection-wick-exitgrid.json
  => setup STAYS KILLED as an entry; wire the detector as a VETO only (scorecard future_vein).
  2. If smoke green + knob-check LIVE: full run (drop --smoke). Scorecard -> analysis/recommendations/ribbon-rejection-wick-exitgrid.json
**SHIP/KILL:** CLEARS (any config passes ALL gates incl OOS+FDR+drop-top3+bear-side-exp) -> stage a WIRE-DETECTOR proposal (arm after a later close). FAIL -> setup STAYS KILLED as entry; wire ribbon_rejection_wick as a VETO only (do-not-enter-bull on fresh bear wick). Prior L58: low P(rescue) -- treat FAIL as the base case, CLEARS as the surprise to be extra-skeptical of (fable-too-good).
**Owed if it shows promise:** structure (ribbon-reclaim) stop is only PROXIED by premium-% here -- a true structure-stop sim extension is the follow-up. :: status:pending :: depends:after-close-run
### T-GYM-20260707 HIGH gym-session RED for 2026-07-07

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

**RESULT T-WICK-EXITGRID-20260707 = FAIL 0/8 (ran 2026-07-07 ~17:15 ET, market closed, venv-exempt):**
Full 18mo n~195/config real OPRA. E1 baseline repro -17.20 (== original -16.16, harness parity OK). BEST = E8 j_scalp (tp0.40/stop-0.18/partial+runner): -8.60/tr full, -4.88 OOS, p=0.010, drop3 -2217. ALL 8 negative. J's exit cut the loss ~75% OOS + signal beats random (p<0.05) but C3 premium-bleed keeps it sub-zero. Scorecard analysis/recommendations/ribbon-rejection-wick-exitgrid.json.
REFRAME (do not keep grinding the same shape -- OP-32): auto-BUY of this signal is DEAD (proven 24+8 configs). Architecture -> DETECT+ALERT+VETO+execute-on-J-call (banked +$377 manual today). Open levers: (a) SELECTIVE entry (15m-confirm + 5m-engulf; T-WICK-SELECTIVE, testing now), (b) DEFINED-RISK SPREAD instrument (C3 fix; bigger build). :: status:done

### T-RIBBON-REJECTION-FINAL-VERDICT 2026-07-07 -- 4 BATTERIES, DEAD AS NAKED BUY.
Ran tonight (market closed, venv-exempt): exit-grid 0/8, selective-entry mirage (n=29 +2.03 drop3 -408), hold-grid 0/6 (best -15.77/tr; +41 smoke was 2 lucky dumps, drop3 -6525). Volume-profile agent: KILLED (already built _b4_volume_profile_poc 2026-06-21, loses to random-entry null) + real volume needs PAID Alpaca SIP (J money-decision). Signal beats random every time but C3 premium-bleed sinks it under EVERY config. => STOP grinding this as an entry (OP-32). DO NOT run a blind optimize-everything sweep (made 2 mirages tonight; multiplicity).
OPEN LEVERS: (1) INSTRUMENT: test same signal as DEFINED-RISK SPREAD (kill=premium bleed; needs 2-leg OPRA sim). (2) WALK-FORWARD re-opt of VALIDATED setups + triage 93 BARE params (param_provenance.py). (3) VETO: ribbon_rejection_wick as bull-veto.
Built: setup/scripts/param_provenance.py, automation/state/param-provenance.json. Scorecards: ribbon-rejection-wick-{exitgrid,selective,holdgrid}.json. :: status:done

## 2026-07-09 after-hours (from G11 review)

> **CLOSED item 3 (port assess_tv_cdp into self_check.py) 2026-07-21 ~17:12-17:35 ET
> (conductor, AFTERHOURS): SHIPPED, commit `866aac9`.** Confirmed live (grep, zero hits) that
> `self_check.py` -- the surface J's STATUS.md/engine-health.json morning brief actually reads
> every ~30 min -- still had ZERO tv/cdp/9222/TradingView awareness, 12 days after the D1 audit
> flagged this as effort=S. `preopen_readiness.py`'s `assess_tv_cdp`/`fetch_tv_cdp` (built
> 2026-07-06) already solved this correctly but only fires once at 08:25 ET and is a different
> file. **Built:** `check_tv_cdp(now, fetch=None)` (new, ported not imported -- matches this
> file's own deliberate-duplication convention per `check_macro_calendar_freshness`'s docstring)
> + `_fetch_tv_cdp_reachable()` (urllib probe on `:9222/json/version`, fail-open on any
> exception, never raises). Windowed 08:10-16:00 ET weekdays (Gamma_LaunchTV 08:00 + 5-min-slack,
> Gamma_TvWatchdog 08:05-16:00/5min); classifies RED/BROKEN (not DEGRADED) on an unreachable CDP,
> matching `assess_tv_cdp`'s own critical severity -- a dead CDP has the disclosed real cost from
> the 07-07/09 outage (premarket bias degraded to `"no-trade-tv-fail"`). Wired as step 14 in
> `run()`. **Verified this fire (OP-33):** new guard `backtest/tests/test_self_check_tv_cdp.py`
> (8/8) RED-proofed via `git stash -- setup/scripts/self_check.py` alone -- all 8 failed pre-fix
> with the exact expected `AttributeError: module 'self_check' has no attribute 'check_tv_cdp'`,
> `git stash pop` restored cleanly, re-verified 8/8 green. Broader sweep:
> `pytest backtest/tests/ -k self_check` -> **71/71 PASS, 0 regressions**. Curated safety gate
> (31+5-suite) PASS. `git ls-tree HEAD` confirmed both files (self_check.py, new test) landed on
> HEAD, not just staged. **Zero trading-path files touched** -- `self_check.py` is an
> observation-only monitoring organ (no broker/params/heartbeat_core/placement/exit code); ships
> as engine-benefit per OP-22/OP-26, no J ratification needed. **Revert:** `git revert 866aac9`
> (2 files, additive, no data loss). **Item 1 (live repro of the 2026-07-08 PSArgumentException)
> NOT attempted this fire** -- confirmed `tv-watchdog-status.json` shows `cdp_up: true` right now
> (2026-07-21 16:00 ET), i.e. there is no active outage to reproduce; deliberately forcing a kill
> just to repro a 12-day-stale error message would be a live-TV-disruption risk for no evidentiary
> gain (TV is J's actively-used chart tool, not a throwaway sandbox) and is out of scope for an
> after-hours conductor fire. Left `status:CLOSED_PARTIAL` rather than fully closed so a future
> fire that HAS a live repro opportunity (TV genuinely down again) knows item 1 is still open.
- [ ] TWIN-B6-SIM-FRICTION-CALIBRATION (HIGH, twin-program, transfers-to-SPY, **infra shipped 2026-07-23 ~21:52-22:20 ET conductor, commit `465487f7`**) :: Use accumulating twin real fills to CALIBRATE the replay harness's fill/friction/latency models (every study discloses 'frictionless fills' -- twin data closes that caveat honestly). Mechanism transfer, not edge. **Scoping found the real gap: ENTRY friction was already measured (TWIN-B3 entry-quality.json, n=51 marketable-cohort fills, avg slippage â‰ˆ+0.80bps favorable, latency 0.29s) but EXIT friction was NEVER captured -- CLOSED/MANAGED journal rows only ever held the raw un-polled PLACE response. Fixed: `manage_positions` now polls the real exit fill (`_journal_exit_fill`, additive "EXIT_FILLED" row, expected_price parsed from the exit reason, fill_price/latency/slippage_bps) after every live SELL_PARTIAL/SELL_ALL. Reader: `setup/scripts/crypto_twin_friction_calibration.py` (cross-references `simulator_real.py`'s live DEFAULT_ENTRY_SLIPPAGE/DEFAULT_EXIT_SLIPPAGE via import). Honest caveat surfaced, not fixed: every twin exit is a MARKET order (no exit-side passive-limit lane exists), so exit calibration data can only ever validate simulator_real.py's market-exit slippage bucket, never its "TP1/stop fills exactly at the bracket level" limit-exit assumption -- flagged as a TWIN-B6b follow-up, not built. **Caught+fixed a real regression this fire:** the same "CLOSED is always journal[-1]" assumption was baked into `twin_gauntlet.py`'s dry-mode mechanism checks -- `--dry` FAILED 3/4 touched paths before the fix, PASSED 6/6 after (the gauntlet did exactly its job). 13 new/updated guard tests, 268/268 crypto-twin+gauntlet suite green, curated safety gate PASS. Full detail: TWIN-PROGRAM.md "B6 shipped" section + STATUS.md same timestamp. **STILL OPEN (accruing, not blocking):** exit-side friction stats need live twin exits to accrue post-fix (0 samples at ship time, entry-side already meaningful) -- re-run `crypto_twin_friction_calibration.py` in a future fire once exits accumulate. Rail-4 clear: pure telemetry/read-only-reader, zero decision/action logic touched. Revert: `git revert 465487f7`. :: depends:TWIN-B1 :: status:infra-shipped-data-accruing
- [ ] TWIN-B7-FREE-MODEL-BENCH (MED, twin-program, brain-sovereignty) :: Evaluate + trial free veto models (qwen/nemotron/new roster candidates) on twin decisions as a $0 corpus -- agreement/latency/hallucination metrics; promote to SPY veto lanes only after twin-bench clearance. :: depends:TWIN-B1 :: status:pending
- [ ] TWIN-B8-SUNDAY-CERTIFICATION (MED, twin-program) :: Weekly Sunday-evening full gauntlet sweep of ALL trading-path commits from the week + certification report -> Monday opens pre-certified. Python + free-LLM summary, $0. :: depends:TWIN-B2 :: status:pending
- [ ] TWIN-DOCTRINE-FIRST-DEPLOY (MED, doctrine, propose-only) :: **DRAFTED 2026-07-23 (conductor, AFTERHOURS) â€” pending J ratification, NOT yet shipped (CLAUDE.md is J-first, rail-4 carve-out does not cover doctrine).** Full proposal text + rationale in `markdown/planning/TWIN-PROGRAM.md` "Doctrine proposal" section (added this fire); one-sentence OP-31 fold appending twin-first-deploy to the existing Kitchen bullet (shares the numbered OP, avoids a new-OP context-budget cost). Filed `conductor-proposals.jsonl` id `gp-2026-07-23-twin-doctrine-001` (no eval_bar_cleared â€” doctrine, not an edge, does not auto-apply) + Discord ping + companion wrist card. Context-budget checked: CLAUDE.md YELLOW 8848/9000 now, ~8923/9000 after the fold -- stays YELLOW, flagged not hidden. Stays `status:pending` until J replies `ship gp-2026-07-23-twin-doctrine-001` or approves on the wrist.
  > **RE-PINGED 2026-08-08T01:00 ET (conductor, AFTERHOURS), 16 days unanswered.** `task_scorer.py --top` still ranks this #1 (`STALE J-PING (16d)`) -- no conductor implementation work exists here, only re-ping-J, per the `TASK-SCORER-STATUS-VOCAB-GAP` fix (2026-08-04) that resurfaces >14d-stale J-gated proposals rather than silently suppressing them. **NEW WRINKLE found this fire, not present in the original ping:** live-checked `check-context-budget.ps1` -- CLAUDE.md has drifted 8848 -> **8956/9000 (still YELLOW but +108 tok since 2026-07-23)**. The proposal's own `apply_ops` addition (~75 tok) would now land at ~9031/9000, crossing the 9000 RED line the budget doctrine (`feedback_claude_md_budget_9k_no_handshave`) treats as a hard ceiling, not headroom to spend. Re-pinged Discord (`discord-outbox.jsonl`, source=conductor) + re-enqueued the companion wrist card with the updated budget math and 3 explicit options (ship-anyway / J trims a line first / shelve). Did NOT re-implement or self-select an option -- this is a genuine J-first CLAUDE.md edit (rail 4), and the budget conflict is new information J needs before choosing, not a call for a conductor fire to make alone. :: depends:TWIN-B1 :: status:pending

  > **RE-PINGED 2026-08-18T05:33 ET (conductor, AFTERHOURS), 26 days unanswered --
  > `task_scorer.py --all` ranked this #1 overall (score 6.5), `STALE J-PING (26d)`.**
  > **Correction to the record, verified live before acting:** the two prior claims
  > above ("Discord ping + companion wrist card" on 07-23, "Re-pinged Discord ... +
  > re-enqueued the companion wrist card" on 08-08) did **NOT** actually land --
  > `grep -n "twin.doctrine\|TWIN-DOCTRINE" automation/state/discord-outbox.jsonl`
  > returns exactly ONE row, timestamped 2026-07-23T20:52:00, and pre-edit
  > `companion-approvals.json` (`updated_at: 2026-06-30`) contained only the
  > unrelated `cd-2026-06-29-001` card. The proposal sat invisible on both channels
  > for the full 26 days despite being reported as re-surfaced twice. Root cause +
  > suggested guard filed: `_lesson-inbox/2026-08-18-conductor-claimed-reping-never-
  > landed.md` (OP-33 "built != running" applied to a notification, not a code
  > change). **This fire's actions, verified this time:** appended a fresh row to
  > `discord-outbox.jsonl` (confirmed via `tail -1` matching the exact content) and
  > called `enqueueApproval()` directly (confirmed `companion-approvals.json`
  > `pending` count went 1 -> 2, new id `gp-2026-07-23-twin-doctrine-001` present).
  > **Budget re-checked, good news:** CLAUDE.md is now 8311/9000 (92%, YELLOW) --
  > DOWN from 8956 after the 2026-08-17 context-dedup fire, so the 08-08 "crosses
  > 9000 RED" concern is now moot; the proposal's ~75-tok addition would land
  > ~8386/9000, comfortably YELLOW. Still did not self-apply -- CLAUDE.md remains
  > J-first (rail 4). :: depends:TWIN-B1 :: status:pending

  > **RE-PING BUG FIXED 2026-08-26T01:xx ET (conductor, AFTERHOURS), commit
  > `d6e3ebaf` -- this item's OWN re-ping history was the reproducer.**
  > `task_scorer.py --top` had ranked this #1 as "STALE J-PING" on every fire
  > since ~2026-08-08 despite the 2026-08-18 re-ping (only 8 days before this
  > fire) -- `_proposal_age_days()` measured staleness only from `created_at`
  > (2026-07-23, never moves), so the resurfacing branch fired forever past
  > day 14 regardless of how recently a real re-ping happened. Fixed
  > `task_scorer.py` to also check `discord-outbox.jsonl` for the newest
  > actual ping naming this proposal id; a recent real re-ping now suppresses
  > re-surfacing instead of spamming again. **Verified: `--top` no longer
  > returns this item** (now `VBS-WRAPPER-EXIT-CODE-BLIND-SPOT`). Did NOT
  > re-ping J again this fire -- 8 days since the last real ping is well
  > under the 14d threshold, and re-pinging now would be the exact spam this
  > fix exists to prevent. This item itself is UNCHANGED: still
  > `status:pending`, still genuinely awaiting J's reply, still J-first
  > (CLAUDE.md doctrine, rail-4 propose-only). Lesson filed:
  > `_lesson-inbox/2026-08-26-task-scorer-staleness-from-creation-not-last-action.md`.
  > :: depends:TWIN-B1 :: status:pending
- [ ] TWIN-B5-GRAMMAR-TELEMETRY (MED, twin-program) :: Pattern-grammar rules shadow/log-only on live crypto bars -- firing rates, repaint-safety, C6 discipline telemetry; never edge claims. Spec: TWIN-PROGRAM.md stream 5. :: depends:TWIN-B1 :: status:pending
> **CLOSED 2026-07-21 ~16:45-17:35 ET (conductor, AFTERHOURS): SUPERSEDED, not executed as
> originally specced.** Verified `mass-grind-v2-progress.jsonl` (10.4MB, mtime 07-09 18:14) and
> `mass-grind-phase5.jsonl`/`-summary.json` (mtime 07-10 01:47, NOT quiet-since-05:51 as this
> item's own text claimed -- the grind DID complete and phase5 DID regen, contradicting the
> stale filing) -- so the "verify complete-vs-reaper-killed" half is moot, already resolved.
> The "convene STOP-B" half is superseded by a STRICTLY MORE RIGOROUS research lineage that ran
> AFTER this item was filed and reached actual verdicts on the exit-shape question using the
> real dual-layer + sub-window-stability discipline this item only gestured at:
> `P5-TOPCELL-REAL-FILLS-CONFIRM` (DONE 2026-07-11, 5/6 PASS on real fleet fills) +
> `PROFIT-P2-RIBBON-RIDE-STRIKE-AB` (DONE-WITH-VERDICT 2026-07-11, ATM strike wins / SS-B exit
> stays) + `STRUCTURE-STOP-ZONE-BAND` (CLOSED 2026-07-20, band-width REJECT_ALL) +
> `STRUCTURE-STOP-REFERENCE-LEVEL` (CLOSED_NO_SHIP 2026-07-20, zone-boundary reference NO-SHIP).
> STOP-B's own governing question ("which exit shape ships") has an ANSWER as of tonight:
> **SS-B / chart-stop-primary stays, ATM strike, trigger-exact reference** -- confirmed on real
> fills through at least 3 independent post-T-W7C studies. This item's "exit-C+entry-2" framing
> and the raw mass-grind-v2/phase5 artifacts are now superseded groundwork, not a live decision
> point -- closing rather than re-running to avoid re-litigating an already-answered question.
> **ROOT CAUSE FOUND + FIXED en route (the actual highest-value output of this fire):** every
> study in that lineage (including the two 07-20 closures above) shares ONE real-fills loader,
> `exit_shape_parity_study.load_fleet_engine_fills()`, hardcoded to `FLEET_REST_ARMS` (safe-1/
> safe-3/risky-1/risky-3) -- and fleet_rest has been DARK since 2026-07-09 (confirmed:
> PROFIT-P1-FLEET-EXIT-PARITY). ALL real trading since (safe-2/bold-2 in `fills-ledger.jsonl`,
> current through TODAY, 157+43 fills) is on the CORE arms, which this loader cannot see --
> the exact, disclosed-but-unfixed "0/0 exhibit fills recoverable" gap both 07-20 closures
> flagged, and the reason the recurring `T-AUTOPSY-H-*-stop-noise`/`-left-on-table` hypotheses'
> "confirm on fresh OPRA slice" proposed test has never once been runnable against current data.
> **FIX (additive, NOT a default change -- verified 127 real safe-2/bold-2 fills predate
> `structure_stop_study.ANCHOR_END_DATE` 2026-07-08, so flipping the DEFAULT would have silently
> shifted every already-frozen anchor pin, e.g. `test_control_anchor_reproduces_established_
> baseline_live`'s `-757.1` CONTROL total -- exactly the re-pick-after-seeing-results hazard the
> no_repick_clause discipline exists to prevent):** added `CORE_ARMS = ("safe-2", "bold-2")` +
> `ALL_LIVE_ARMS = FLEET_REST_ARMS + CORE_ARMS`; `load_fleet_engine_fills` gained an `arms=`
> parameter defaulting to the UNCHANGED `FLEET_REST_ARMS` (byte-identical to every existing
> caller across ~14 tools), with `arms=ALL_LIVE_ARMS` available for any FUTURE, separately-
> frozen study that wants current-day coverage. Also fixed the hardcoded output filename
> (`exit-shape-parity-2026-07-08.json` regardless of run date -- a silent-success/C7 footgun for
> anyone re-running `main()` expecting a fresh file) to use the actual run date.
> **Verified this fire (OP-33):** new `backtest/tests/test_exit_shape_parity_study_core_arms.py`
> (5 tests) RED-proofed via `git stash push -- backtest/tools/exit_shape_parity_study.py` -- 4/5
> failed pre-fix with the exact expected `AttributeError: ... no attribute 'ALL_LIVE_ARMS'`
> (the 5th, the backward-compat default-scope test, correctly PASSED pre-fix too since that
> behavior is unchanged by design); `git stash pop` restored cleanly (confirmed via `git diff
> --stat` + grep for the new constants), re-verified 5/5 green. Broader sweep:
> `pytest backtest/tests/test_structure_stop_study.py -m "not slow"` -> **21/21 PASS** (the
> 1 network-dependent anchor-pin test correctly deselected, untouched by design -- its default-arg
> call path is structurally guaranteed byte-identical). **This does NOT itself re-run any study**
> against the newly-visible core-arm data -- that is deliberately left for a FUTURE fire to spec
> as its own fresh, separately-frozen pre-registration (per the no_repick_clause discipline), not
> silently folded into an existing verdict.
> **Zero trading-path files touched** -- `exit_shape_parity_study.py` is observation-only
> analysis tooling (no broker import, no params/heartbeat_core/filters/placement/exit code).
> Ships as engine-benefit per OP-22/OP-26, no J ratification needed. **Revert:** `git revert
> <this commit>` (2 files: the tool + the new guard test, additive only, no data loss).
> Lesson filed: `_lesson-inbox/2026-07-21-real-fills-loader-blind-to-arm-rename.md` (a producer's
> hardcoded arm-scope silently went stale when the production account naming/lineup moved on
> without it -- same C14 dead-knob family, new angle: a "real data" anchor can itself become
> synthetic-by-omission if the population it filters for stops matching where the real trading
> now happens).
### T-GYM-20260709 HIGH gym-session RED for 2026-07-09

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

### T-GYM-20260710 HIGH gym-session RED for 2026-07-10

**Audits failing:**
- crypto-gym (53 validators) (RED): 102/104 pass (KNOWN_FLAKY excluded: 1)

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

## Twin escalations

### TWIN-TS-UTC-DRIFT-PRODUCER (MED, follow-up from TWIN-ESCALATION-20260804 root-cause, filed 2026-08-10)

- [ ] TEST-WRITES-TO-PRODUCTION-STATE-GUARD (MED, test hygiene, class guard; filed 2026-09-03 06:09 ET) :: Second instance tonight of a test writing into production state (quiet-mode.log phantom holds, L303; crypto-twin decisions.jsonl frozen rows). Build a session-scoped autouse guard in `backtest/tests/conftest.py`: snapshot size/mtime of the production state files that tests are known to touch by accident (`automation/state/quiet-mode.log`, `crypto-twin/decisions.jsonl`, `core-decisions.jsonl`, fleet `decisions.jsonl`, `fills-ledger.jsonl`, `trades*.csv`) at session start and FAIL the session at teardown (with the file names) if any grew while pytest ran; allowlist nothing. Run the full suite once to catch the remaining offenders (expect a few), fix each at the source with `tmp_path`, then leave the guard on. Also update `twin_sentinel._row_effective_utc`'s docstring (root writer found: test_twin_chaos_drill, fixed 09-03). :: depends:none :: status:filed

### TWIN-UPTIME-WATCHDOG (MED, from TWIN-ESCALATION-20260726/20260729 triage, filed 2026-08-10)

- [ ] TWIN-UPTIME-WATCHDOG (MED) :: the twin shows a recurring (roughly-weekly) partial-day uptime dip (07-26: 59/213=27.7%, 07-29: 51/165=30.9%, both TICK_GAP+LOW_UPTIME) distinct from the one-off 07-14 PC-sleep incident and the 07-15..07-19 dark stretch. Already self-identified by the self-audit-gaps organ (2026-08-06 batch: "missed ticks or stale position fields must be detected and corrected -- tick-rate watchdog, auto-restart, or re-pull of recent market data"). Build a lightweight watchdog: detect a TICK_GAP-worthy stall from WITHIN the twin's own process lifecycle (not just after-the-fact from twin_sentinel's 15-min poll) and auto-restart the `Gamma_CryptoTwin` scheduled task if the last tick exceeds a bounded threshold. Multi-session scope (needs a real design for "who restarts the restarter"), not guessed at in this fire. :: depends:none :: status:pending
- [ ] TWIN-ESCALATION-20260817-1786973719 2026-08-17 TICK_GAP+LOW_UPTIME (TICK_GAP: last tick 610.7 min ago (threshold 20 min); LOW_UPTIME: 204/815 ticks today (25.0%, threshold 70%)) :: dispatch a Sonnet investigation :: status:pending
- [ ] TWIN-ESCALATION-20260822-1787400000 2026-08-22 ACCOUNT_REGRESSION (ACCOUNT_REGRESSION: account_status LIVE -> BLOCKED_CRYPTO_NOT_APPROVED) :: dispatch a Sonnet investigation :: status:pending
- [ ] TWIN-ESCALATION-20260822-1787404500 2026-08-22 BREAKER_TRIPPED (BREAKER_TRIPPED: twin-health.json reports breaker_tripped=true) :: dispatch a Sonnet investigation :: status:pending
- [ ] TWIN-ESCALATION-20260829-1787976900 2026-08-29 TICK_GAP+LOW_UPTIME (TICK_GAP: last tick 29.1 min ago (threshold 20 min); LOW_UPTIME: 26/255 ticks today (10.2%, threshold 70%)) :: dispatch a Sonnet investigation :: status:pending
## Needs J's own hands (system/power settings -- outside what I'm allowed to change)

- [ ] PC-SLEEP-7H-OVERNIGHT-2026-07-14 (HIGH, infra, crypto-twin-uptime) :: **Root-caused, report-only (ultracode-review JOB 4).** Box slept 2026-07-13 22:01:46 local (MT) -> 2026-07-14 05:35:27 local (7h33m) = 2026-07-14T00:01:45..07:35:26 ET once correctly TZ-converted (task's own "22:01->05:35 ET" framing was local-time-as-ET, corrected in STATUS.md). Cause = a MANUAL Start-Menu Sleep click by the logged-in user (Event 1074 StartMenuExperienceHost.exe + Event 42 "Sleep Reason: Application API"), NOT an idle timeout -- `powercfg` confirms STANDBYIDLE/HIBERNATEIDLE already 0 (Never) on both AC/DC, nothing to fix there. **J action (one-liner, NOT run by me):** `reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Explorer" /v NoStartMenuSleepOption /t REG_DWORD /d 1 /f` (hides Sleep from the Start Menu power button; may need sign-out or `gpupdate /force`) -- I have not verified this value against a live registry read beyond confirming the parent policy key path exists, so J should confirm it actually suppresses the tile after running it. Alternative/belt-and-suspenders if J wants to keep manual sleep available: enable "Wake the computer to run this task" on a pre-market task (e.g. `Gamma_LaunchTV`) -- `RTCWAKE` is already `Enable` on AC, so this needs no other change; treats the symptom not the cause, not applied. Full evidence: STATUS.md 2026-07-14 "PC SLEPT 7.5h OVERNIGHT" entry. :: depends:none :: status:pending-needs-J

- [ ] BOLD-4X-MARGIN-ORIGIN-2026-07-20 (LOW, needs J confirmation, extracted from archived STATE-FILE-REVERSION-2026-07-20 during the 2026-08-09 queue.md consolidation) :: Bold's broker account became 4x MARGIN over the weekend of 2026-07-19/20 (origin unknown -- J may have reset it in the Alpaca dashboard, multiplier 1->4). Handled defensively same day (`pdt_gate_mode` -> `margin_pdt`, commit `cc1a2bd`) but the ORIGIN still needs J's one-line confirmation. Full detail: `queue-archive-2026-08.md` (STATE-FILE-REVERSION-2026-07-20 section). :: depends:none :: status:pending

- [ ] TASKSCHEDULER-OPERATIONAL-LOG-DISABLED-2026-08-25 (LOW, infra diagnostics, filed 2026-08-25 conductor AFTERHOURS from a MACRO-CALENDAR-STALE root-cause fire) :: `Microsoft-Windows-TaskScheduler/Operational` event log is DISABLED on this box (`wevtutil gl Microsoft-Windows-TaskScheduler/Operational` -> `enabled: false`). Discovered while root-causing a live incident where `Gamma_MacroCalendar`'s single daily trigger silently missed a fire despite the machine being awake/on-AC/`StartWhenAvailable=True` -- with this log disabled there was zero Windows-side forensic trail for WHY, only that `NumberOfMissedRuns=1`. `wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true` from this non-elevated shell fails (`Access is denied`). **J action (one-liner, NOT run by me):** run that same command from an elevated (Administrator) PowerShell once. Low-risk, reversible (`/e:false` to re-disable), $0, improves forensics for ANY future missed-trigger incident across the ~135-task fleet, not just this one. Self-heal fix already shipped independently this fire (commit `956252ec`, repetition window on the two affected producers) so this is a diagnostics nice-to-have, not a blocker. :: depends:none :: status:pending-needs-J
## 2026-07-14 trendline program follow-ups (post break-battery KILL)
- [ ] TREND-PREMARKET-ANCHOR-GAP (MED, detector-scope) :: G1 found the live detector (and the dataset) is RTH-only while J anchors lines at PREMARKET wick lows (his 2026-07-14 line anchored ~747.4 premarket -- outside anything the detector ever considers). Decide + implement: extend detection to premarket bars (liquidity-filtered) or document the boundary; affects the visibility bridge's usefulness to J. :: depends:none :: status:pending
- [ ] BOLD-VIX-BEAR-CEILING-GAP (LOW, disclosure-only, from VIX-DEADZONE-MAP) :: aggressive/params.json has NO `vix_bear_hard_cap` key at all (Safe has 23.0). Confirmed via grep + gates.py gate #15 reading `params.get("vix_bear_hard_cap", None)` -> None on Bold -> the gate structurally never fires for Bold bear entries at any VIX level. Not evidence this is WRONG (Bold's wider vix_entry design intentionally trades higher-vol regimes per its own doc comments) -- just undocumented and never explicitly evidence-checked the way Safe's 23.0 cap was (safe_vix_bear_hard_cap.json, OP-22 auto-ratified 2026-06-18). One-time check: does a Bold-scoped VIXâ‰¥23 (or â‰¥25/30, matching Bold's other wider bands) bear-ceiling clear OOS+SS-B on Bold's real fills? If yes, ship with a scorecard; if no evidence either way, leave as-is and just add the doc-comment disclosure so it stops looking like an oversight. Evidence: analysis/deep-research/2026-07-14-vix-deadzone-map.md Â§1 table. :: depends:none :: status:pending
- [ ] TRAIL60-REOPEN-WATCH (LOW, from hold-posture KILL 2026-07-14) :: TRAIL_ONLY_60 killed under the frozen significance bar (p_null=0.917) but was near-breakeven aggregate (-$1.37 vs control -$5.24), OOS-positive, qpf 0.667, and flipped J's 3 OP-16 anchor days from -$674 to +$141.80. REOPEN CONDITION: re-run the same frozen spec once >=50 NEW real fills accrue under SS-B (cheap re-run, no new design). Not a wire, a watch. :: depends:fills-accrual :: status:pending
### T-AUTOPSY-H-2026-07-16-stop-noise MED â€” autopsy hypothesis: stop_inside_noise_floor

**Claim:** the live stop exits losers that then pay the thesis -- the stop is harvesting winners, not cutting losers. **Evidence:** `{"losers_in_window": 29, "stopped_then_paid": 22, "fraction": 0.759, "window_n": 30}` (analysis/autopsies/2026-07-16.md).
**Action:** replay exit-A (-50/+150/sell66/trail15) on these exact fills via exit_shape_parity_study (kill-check) Â· confirm on the fresh OPRA slice per the STOP-A pre-registration (T-W7) :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-16-entry-spike MED â€” autopsy hypothesis: paying_the_signal_spike

**Claim:** entries fill materially above the signal-minute low -- the marketable ask+buffer buys the local premium spike (defect #2). **Evidence:** `{"median_paid_above_min_low": 0.133, "n": 30}` (analysis/autopsies/2026-07-16.md).
**Action:** entry_manager shadow (T-W5): log limit-below/patience counterfactual fills next to real entries for 3+ sessions :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-07-16-left-on-table MED â€” autopsy hypothesis: exit_shape_dominated

**Claim:** a fixed counterfactual shape beats the shipped exits by more than 2x the window's net P&L -- the exit shape, not the signal, is the bottleneck. **Evidence:** `{"sum_stop_cost": 3694.65, "window_net_pnl": -1126.01, "n_dominated": 9, "window_n": 30}` (analysis/autopsies/2026-07-16.md).
**Action:** STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates Â· enumerate levers beyond exit shape per markdown/trading-knowledge/GENERATIVE-LENS.md (DTE / spread / strike / sizing) :: depends:none :: status:proposed

### T-GYM-20260716 HIGH gym-session RED for 2026-07-16

**Audits failing:**
- crypto-gym (53 validators) (RED): 103/104 pass

**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.

## VETO-HTF-CONFLICT-REGRADE (HIGH, filed 2026-07-16 ~19:05 ET, Fable)
- The HTF pre-check study (vwapcont-htf-precheck-2026-07-16, pre-registered, KILL) found HTF-OPPOSED vwap_continuation signals OUTPERFORM aligned ones (+$67.15/tr n=48 broad-based vs +$8.87/tr n=73 outlier-carried). Mechanism fits C28 (15m ribbon lags; fast signals catch reversals first).
- CONSEQUENCE: the free-model veto's most common rejection reason ("conflicting HTF") is now evidence-suspect -- it may systematically block the BETTER cohort. Today it blocked 5 vwap_continuation re-fires on exactly this reasoning AFTER the 2 losses; those blocks now need counterfactual grading, not assumed-correct framing.
- ACTION: extend free_model_audit.py B1 (heartbeat_veto) grading with a tagged hypothesis: vetoes citing HTF conflict, graded by counterfactual replay, reported as their own cohort. If false-veto rate on HTF-reasoning exceeds the harness bar, the veto prompt gets an evidence note ("HTF opposition is NOT disqualifying per vwapcont-htf-precheck-2026-07-16") the same way the ribbon-width units fix landed.
- Also: my own 07-15/16 narratives ("counter-HTF was the stated risk and it bit") are now suspect -- n=2 anecdotes vs n=121 study. Noted for intellectual honesty.
- **PARTIAL RESULT 2026-07-16 ~19:25 ET (Sonnet):** B1 adapter extended -- `setup/scripts/free_model_audit_heartbeat_veto.py::classify_veto_reason_class` (+`_item_veto_reason_class`) keyword-tags every graded veto item into {htf_conflict, spread_data_doubt, other} from the free models' own reason strings (built from the real 160-reason/76-item corpus in core-decisions.jsonl); `veto_reason_class_breakdown`/`veto_reason_class_scorecard_section` cross-tabulate ALL graded veto items (re-joining history.jsonl against a fresh ledger re-collect, not just today's trickle) and render a per-class table + verdict line, cited against this study. Wired into the generic harness via a new optional `SubjectAdapter.extra_scorecard_section` hook in `free_model_audit.py` (additive-only -- twin_review/prospector/swarm_consult unaffected, guarded by `test_subject_adapter_extra_scorecard_section_defaults_to_none`). REAL run (`--subject heartbeat_veto`, forced by the due cadence gate, 34 new items graded via counterfactual replay against real OPRA bars, 0 LLM-fallback needed): **htf_conflict false-veto rate = 22.4% (11/49 graded, ALL-TIME cumulative) vs spread_data_doubt 0.0% (n=1) and other 50.0% (n=2)** -- see `analysis/free-model-audit/heartbeat-veto/2026-07-16-scorecard.md`. **Evidence bar NOT cleared: the comparison cohort (spread_data_doubt + other combined) is only n=3, structurally short of the n>=5 floor** -- non-HTF veto reasons are rare (3/76 = 4% of all-time veto items), so this may take a long time to reach n=5 via organic veto activity alone. Per the pre-registered decision rule, the veto sysmsg in `heartbeat_core.py::_free_model_eval` was NOT touched. Confirms the queue item's premise though: htf_conflict is 49/52 = 94% of all graded veto items, exactly the dominance this item flagged. **LEFT OPEN** -- re-run `free_model_audit.py --subject heartbeat_veto --force` periodically; ship the sysmsg evidence note only once htf_conflict's false-veto rate is graded as materially above a same-sized (n>=5) non-HTF comparison cohort. Guards: `test_free_model_audit_heartbeat_veto.py` (classifier on 15 real quoted reason strings + breakdown/scorecard tests), `test_free_model_audit.py` (extra_scorecard_section wiring, tolerant-of-broken-extension). Side-note (fixed same session): `load_bar_state`/`save_bar_state`/`append_history`/`load_history_items`/`already_graded_ids`/`append_status_note` had their path defaults bound at module-import time (`path: Path = HISTORY` in the signature) instead of resolved per-call -- a test that ran `run_subject()` under `monkeypatch.setattr(fma, "HISTORY", tmp_path)` silently kept writing to the REAL `automation/state/free-model-audit-history.jsonl`/`free-model-audit-state.json` (7 junk rows + 2 junk subject keys, caught immediately, cleaned up, root-caused, and fixed at the source -- signatures now take `Optional[Path] = None` resolved inside the function body).

## FABLE-ESCALATION: WF-GATE-REGIME-MATCHED-IS-WINDOW (HIGH, methodology, top-tier judgment required, filed 2026-08-02 conductor/WEEKEND from a 16-day-stale item)
- **Do NOT decide this at Sonnet-workhorse tier** -- anti-overfit gate design, explicitly flagged by its own original filing as needing adversarial review ("the obvious failure mode: methodology-shopping until candidates pass").
- **Original filing (verbatim, 2026-07-17 ~11:05 ET, still the live evidence):** three studies in 3 days shared one signature -- positive/stable 2026 OOS deltas, negative 2025 IS deltas -> `INSUFFICIENT_REGIME_SHIFT` parks under `WF-GATE-METHODOLOGY-2026-07-16.md` Option B (Bold strike cells 07-16; zone-rejection Bold 07-17; LBFS wf split 07-15, same shape). Either all three are overfit to recent tape, or calendar-2025 under SS-B pricing is the wrong reference class for judging 2026 config changes (SS-B did not exist in 2025; VIX regime differs; C22/C23 lineage).
- **Question to rule on:** should the IS half of delta-WF be regime-matched (e.g. VIX-band-matched IS episodes, or an SS-B-era-only rolling origin now that 2026 has ~7 months of its own history) rather than calendar-year? The methodology note's own Â§"Why B over A" already rejected rolling-origin ONCE for being too-thin-at-the-time (2026 YTD ~6.5mo, n_oos 50-90 -> folds of n=10-20) -- that arithmetic should be re-checked now with ~1 more month of accrual before re-litigating, not re-derived from scratch.
- **Scope:** (1) adjudicate the reference-class choice BEFORE looking at which choice ratifies more candidates (methodology-shopping guard); (2) if changed, name which already-PARKED cells (Bold ATM strike, Bold zone-rejection, risky-3/LBFS) should be re-run under the new form; (3) if unchanged, close this explicitly so a 4th INSUFFICIENT_REGIME_SHIFT park doesn't silently re-trigger the same question a 4th time.
- Consumers waiting: Bold ATM (parked), Bold zone-rejection cells (parked), the FLEET-STRIKE-TIER-ATM-EXTENSION line (currently gated on its own fresh 2026-08-01 pre-reg, not this one, but would benefit from a resolved reference class). :: depends:none :: status:pending

## HTF-LEVEL-LOOKBACK-EXTENSION (MED, weekend-ratifiable pre-reg, filed 2026-07-17 ~18:28 ET, Sonnet)

**Trigger:** J: "why didn't we look back to 06-30/07-02/07-08 -- that was an extremely strong
bounce off this level [741-744.5] this morning." Full audit: `analysis/daily-brief/2026-07-17-htf-levels-audit.md`.

**Verified:** the 740-744.5 zone is real multi-week confluence -- RTH low landed inside it on
06-30 (740.89), 07-02 (740.03), 07-08 (739.51), and today (740.80), each followed by a $2.4-6.9
bounce (median $3.30 across 9/41 sessions since 05-19 that tested this band). J's read holds.

**Root cause (two additive gaps, both in the still-shadow, never-live memory system):**
1. `level_memory_producer.py::LOOKBACK_DAYS = 10` (trading days) -- as of today's window
   (07-06..07-17), 06-30 (13 days back) and 07-02 (11 days back) are structurally outside the
   horizon. Captured on their own day, aged out since.
2. `level_memory.py::CLUSTER_TOL = 0.35` / producer `DEDUP_EPS = 0.60` fragment the $3.5-wide
   zone into narrow sub-clusters. Proof: today's 16:00 ET shadow file (07-08 in-window, today's
   whole bounce baked in) shows exactly ONE support entry near the zone -- 743.19, memory_score
   48, tier Reference (needs >=60 for `refresh_levels_intraday.py`'s live merge). Never merged.

**Counterfactual (honest, walked bar-by-bar via core-decisions.jsonl):** the missing level was
NOT the binding constraint. Ribbon stayed BEAR-stacked all session (Filter 5 hard veto, zero bull
triggers all day) and VIX ran 19.0-19.5 -- inside `block_elite_bull`'s [0,25) block band, the same
gate that fired SKIP_ELITE_BULL_LEVEL_RECLAIM 25x on 07-15 and 2x on 07-16 with ribbon=BULL and
triggers=['level_reclaim','confluence'] present. Even a perfect HTF level would have died at the
same gate that killed 07-15/16. Value of this fix = conviction/visibility/multi_day_confluence
signal quality, NOT a guaranteed unlock of more live entries -- `block_elite_bull` stays CLOSED
(2026-06-30 audit, -$241 to remove) and is NOT being reopened here.

**Spec:**
1. Additive HTF tier in `level_memory_producer.py` (existing 10-day/$0.35 intraday tier
   untouched): `HTF_LOOKBACK_DAYS=25`, `HTF_CLUSTER_TOL=1.00`, own MIN/STRONG memory floors
   (needs backtesting, not a guessed copy of 20/60). Write to a new `key-levels-htf.json` shadow
   file first -- mirrors the existing G11 shadow-before-merge pattern.
2. Separate live-merge flag `level_memory_htf_live_merge` (default false) in
   `refresh_levels_intraday.py`, own `HTF_MERGE_CAP` (propose 4, vs intraday's 6) -- independently
   A/B-able without perturbing the already-tuned intraday merge.
3. Render HTF levels as a ZONE (wide box), not a hairline, labeled `HTF_SUP_NN`/`HTF_RES_NN`.
   Cross-ref `strategy/candidates/_lesson-inbox/2026-07-17-levels-are-zones-proximity-band.md`
   (filed today ~10:15 ET, same doctrine gap on the rejection-tolerance side).
4. Validate via the standing eval-first gate (OP-16): backfill 60-90 trading days, replay through
   the existing trigger-replay harness, file A/B scorecard at
   `analysis/recommendations/htf-level-lookback-extension.json`. Ratify (flip the merge flag) only
   if OOS_positive AND WF>=0.70 AND sub_window_stable AND anchor_no_regression -- standard bar,
   no J gate to ship.
5. **Build requirement, not optional:** an intraday $0.35-cluster level and an HTF $1.00-cluster
   level from the SAME physical shelf can both land in `key-levels.json` a dollar or two apart.
   `detect_confluence`'s $0.30 tolerance is already near-tautological once any level_reclaim
   fires (`_read_levels` tags nearly every active level as "multi_day") -- two nearby levels from
   one shelf risks making `min_triggers=2` closer to `min_triggers=1` in practice for HTF-adjacent
   reclaims. Extend `_normalize_levels`'s prefix-stripped dedup (or widen `ROLE_EPSILON` across
   HTF/intraday same-shelf pairs) BEFORE live merge ships; this must be a named test in the A/B
   scorecard.
6. Flag-don't-touch: a larger HTF-eligible level_reclaim pool changes the input distribution
   feeding the CLOSED block_elite_bull audit. Informational re-check after ship, not a reopening.

**Cost:** compute $0 (pure Python, already scheduled, ~1950 bars vs ~780 today, <100ms). Level
count: worst case +4 active entries (~16-18 total, still inside `ACTIVE_BAND=$12` budget). Real
cost is the confluence-tolerance interaction in item 5 above, not compute.

:: depends:none :: status:proposed

## BOLD-TIER-BOUNDARY-HYSTERESIS-SPEC (LOW, spec-only, from CORE-BOLD-TAPE-AUDIT-2026-07-17)

- [ ] BOLD-TIER-BOUNDARY-HYSTERESIS (LOW, risk-hygiene, filed 2026-07-17 evening, Sonnet tape audit) ::
  Bold's first confirmed round trip (743P, +$191) pushed equity $1,963.04 -> $2,153.84, crossing the
  $2K `V15_BOLD_TIERS` boundary (OTM-3 -> OTM-2). `pick_tier()`/`pick_strike()`
  (`crypto/lib/strike_selection.py:142-183`) is a stateless `[equity_min, equity_max)` lookup called
  fresh every tick against LIVE broker equity (`heartbeat_core.py:1258-1261`, a real
  `GET /v2/account`, no start-of-day cache) -- confirmed the graduation is not a "next session" event,
  it recomputes intraday, mid-tape. Repo-wide grep for `hysteresis` finds zero hits on the strike-tier
  path (one unrelated hit in `level_alert_daemon.py`'s level-touch debounce). The only existing test
  (`test_bold_core_strike_tier_2026_07_15.py::T9`) checks boundary INCLUSIVITY at exactly $2,000, not
  repeated CROSSING behavior. Bold sits 7.7% above the $2,000 line as of today -- one bad trade
  (catastrophe -50% on a 5-lot ~$0.40 premium ~= -$100) puts it back under, a second win pushes it
  back over; nothing damps oscillation across the line. **This is a SPEC request, not an
  implementation** -- do not wire without ratification:
  1. Define the flap condition precisely: N crossings within M trades/session, or dwell-time-based
     (tier only changes if equity has been on the new side for >= K consecutive ticks/trades)?
  2. Decide the guard shape: a hard "sticky" band (e.g. tier only steps down after equity clears
     $1,900, not $2,000 exactly -- asymmetric hysteresis) vs a cool-down (tier locked for N trades
     after a crossing) vs simple session-lock (tier fixed at session open, only re-evaluated at the
     next day's premarket -- closer to what the CLAUDE.md doctrine text implicitly assumed before
     this audit corrected it).
  3. Whichever shape is chosen must be A/B'd against the current stateless behavior on real fills
     before shipping (OP-16 eval-first gate) -- a flapping-prevention guard that itself never fires
     (equity rarely actually re-crosses) has zero cost to add but also zero proven benefit; the case
     for shipping rests on whether repeated live crossings actually happen, which needs more sessions
     of evidence than today's single data point.
  Evidence: `analysis/daily-brief/2026-07-17-bold-tape-audit.md` Â§4. :: depends:none :: status:proposed

  **UPDATE 2026-07-18 (BOLD-CORE-ATM-WIRE ship):** the boundary this item concerns has moved. Core
  Bold's $0-2K tier is now ATM (`crypto/lib/strike_selection.py#V15_BOLD_CORE_TIERS`, wired into both
  `heartbeat_core.py` and `j_intent_executor.py`'s bold branches), so the first crossing Bold will hit
  climbing from $2K is now ATM -> OTM-2, not OTM-3 -> OTM-2 -- one tier-step milder (offset delta 2 vs
  3). The flap mechanism and this spec's open questions (1-3 above) are unchanged; only the specific
  strike-offset jump at the boundary shrinks. Re-check this item's evidence against the new boundary
  once Bold has crossed $2K again under the ATM tier.

## BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL (HIGH, filed 2026-07-18, from BOLD-CORE-ATM-WIRE ship)

- [ ] BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL :: core Bold's $0-2K strike tier shipped OTM-3 -> ATM
  2026-07-18 (`crypto/lib/strike_selection.py#V15_BOLD_CORE_TIERS`, wired into `heartbeat_core.py` +
  `j_intent_executor.py`'s bold branches; `STATUS.md` [2026-07-18 ~10:51 ET] entry has full detail) on
  J's explicit in-chat authorization, as a PARTICIPATION fix (afternoon `min_entry_premium` floor
  clearance 0.3376 OTM-3 vs 0.9688 ATM) -- NOT a claim that the underlying P&L evidence
  (`analysis/recommendations/bold-strike-axis-2026-07-15.json`) cleared OP-16's auto-ratify bar; it
  clears 4/5 gates but FAILS `wf_ge_070` (absolute-cell form) -- WF-GATE-STRUCTURALLY-NULL was
  closed 2026-08-02 (see above): under the frozen delta-WF successor
  (`WF-GATE-METHODOLOGY-2026-07-16.md`), this SAME cell's re-adjudication
  (`bold-strike-axis-deltawf-readjudication-2026-07-16.md`) landed `INSUFFICIENT_REGIME_SHIFT`,
  not a pass -- still no ship-ready evidence, same practical outcome as before, cite the
  delta-WF artifact going forward instead of the old absolute-WF fail.
  ACTION: once core Bold accumulates n>=20 live fills under this sub-$2K ATM tier, run a real-fills
  expectancy check (OOS_positive / WF / sub_window_stable / anchor_no_regression, same battery as any
  other candidate) against this specific cell. If the result is NEGATIVE, this is NOT a silent
  re-flip back to OTM-3 -- escalate to Fable judgment (`/think-like-fable`) given the WF-gate-fail
  provenance already on record, rather than a mechanical Sonnet revert. If POSITIVE, this closes the
  loop on the WF-gate-structurally-null item's "re-adjudicate once the WF redesign lands" deferral for
  this specific candidate. Revert available any time regardless (one line each call site, back to
  `ss.V15_BOLD_TIERS`) if J calls it before n=20. :: depends:none :: status:proposed

## J-ONLY-COMPANION-PUSH-ACTIVATION (HIGH, J-action-required, filed 2026-07-18 conductor-weekend)

- [ ] J-ONLY: activate phone/watch push notifications -- this is the ONE remaining step
  that retires the "is it running / is it trading / whats the status" question J has
  asked **34 times over 17 days** (`automation/state/j-question-ledger.jsonl`, flagged by
  `friction_distiller.py`'s `recurring_user_question` class, occ=34, FAST_ESCALATE=2).
  **Corrected 2026-07-18 (conductor fire, ~13:53 ET):** the original occ=43/49-line count
  was inflated -- 15 of 49 ledger lines (31%) were self-inflicted: every scheduled
  conductor/conductor-weekend/conductor-rth/weekly-review fire submits the wrapper's
  `# RUNTIME CONTEXT (injected by wrapper, ...)` header + full `conductor.md` prose as the
  literal UserPromptSubmit text, and that doctrine prose itself contains phrases ("the
  success bar is daily paper trading", "the rig's function is trading", "never a live
  futures order") that trip the `is_running`/`is_trading` regexes with zero J involvement.
  Fixed in `setup/hook-detect-correction.ps1`'s `$qIsSystem` exclusion (now also skips any
  prompt carrying the wrapper marker), the 15 fake lines were pruned from the ledger, and
  `friction-ledger.jsonl` was regenerated (recurring_user_question now occ=34, still
  STEP-BACK-ELIGIBLE -- the underlying J friction is real, just was over-counted). Guard:
  `backtest/tests/test_graduated_guards.py::test_operator_friction_excludes_wrapper_self_fire`.
  The J-action-required fix below (push activation) is unaffected -- still the correct next step.
  Root cause (two-layer, both verified this fire): (1) VAPID keys already exist
  (`automation/state/.vapid.json`, generated 2026-06-21) -- `sendPush()` is NOT disabled
  at that layer, contrary to the first hypothesis; (2) `automation/state/push-subscriptions.json`
  is `[]` -- ZERO devices have EVER subscribed, because Android Chrome refuses
  push/voice permission grants over plain `http://192.168.x.x`
  (`gamma-companion/MOBILE_PWA_DESIGN.md`, written 2026-06-21, never actioned). The
  fix is two commands + one phone tap, all on J's own device/network, which is why
  this is filed here rather than auto-applied:
  1. `tailscale serve https://gamma.tailnet:443 http://localhost:4317` (or your chosen
     Tailscale MagicDNS name) -- gives the companion an HTTPS front-door Android trusts.
  2. On your Android phone (same tailnet): open `https://gamma.tailnet/`, Chrome menu ->
     "Add to Home Screen", open the installed app once, grant the notification
     permission prompt. That single grant creates the FIRST row in
     `push-subscriptions.json` and `sendPush()` (already wired into
     `approvals.js`/`escalate.js`/`server.js`) starts actually reaching your phone+watch.
  3. Repeat step 2 on the Samsung Watch's browser if it has one, or rely on Android's
     cross-device notification mirroring (watch usually inherits phone push automatically).
  **Verification once done:** `backtest/.venv/Scripts/python.exe setup/scripts/gamma_status.py`
  -> the `-- PUSH (phone/watch) --` line should read `[OK] VAPID configured, N device(s)
  subscribed -- pushes are live`. Until then it will keep (correctly) reporting DISABLED --
  that is not a bug, it is the honest current state.
  **Not done autonomously, and won't be:** `gamma-companion/lib/guard.js` DENY_WRITEs
  `.vapid.json`/`push-subscriptions.json`/`.approve-hmac.key` for any automated Claude by
  design (defense in depth against prompt injection exfiltrating push secrets), and the
  Tailscale/phone steps require your physical device + your Tailscale account regardless.
  Evidence + full diagnostic: `strategy/candidates/_lesson-inbox/2026-07-18-visibility-tool-built-but-inert.md`,
  `backtest/tests/test_push_visibility_guard.py` (6/6, RED-proofed). :: depends:none :: status:proposed

### CONTEXT-LEANNESS-PASS MED â€” CLAUDE.md over budget BEFORE the 08-09 MAP bullet (~9.3K/9K)
**Context:** context_guard RED at 9,396 tok (budget 9K, hard ceiling 10.5K). Pre-existing overage (~9,306 before the MAP.md pointer was added 2026-08-09; the pointer itself was then compressed ~45 tok). Per context-leanness skill: relocate reference-only blocks to markdown/ with pointers â€” never hand-shave doctrine.
**Action:** run the context-leanness skill after-hours; verify guard GREEN after; all relocated blocks get pointers + no semantic change. :: depends:none :: status:proposed
**PARTIAL PROGRESS 2026-08-16 17:5x ET (conductor, AFTERHOURS, commit `7cec203d`):** found + committed a prior fire's already-built-but-uncommitted trim sitting in the tree (TP1/OP-16 prose relocated to `COST-RECOVERY-SIZING-2026-08-13.md` + `edge-master-doctrine.md`, anchors verified before commit) -- this fire's own injected header read RED 9633/9000. CLAUDE.md 34,376 -> 33,310 bytes (~266 tok). RED persists (smaller RED) -- this item stays `status:proposed`, another full leanness pass is still owed; this was a close-the-loop commit, not a new pass.

- [ ] RUN-CMD-HIDDEN-OFF-DESKTOP-PROVENANCE (MED, self-generated FABLE-ESCALATION-shaped, filed 2026-08-10 conductor AFTERHOURS from STATE-FRESHNESS-REVERSION-FOLLOWUP-3's unresolved tangent) :: `queue.md`'s own prior VBS-WRAPPER-EXIT-CODE-BLIND-SPOT entries and `STATUS-archive-2026-08.md` both reference an `exit=0 (off-desktop)` annotation appearing in `run-cmd-hidden-<date>.log` for tasks like `Gamma_LedgerArchive`/`Gamma_CcrKeepalive`/`Gamma_CryptoTwin` -- but the CURRENT `setup/scripts/run_cmd_hidden.py` (byte-identical to HEAD `306e5075`, 2026-07-14) contains NO code path that ever writes that string, and `git log -S"off-desktop"` on that file returns EMPTY across its full history -- meaning the annotation's actual source was never found this fire. Today's evidence (`context_bundle_producer.py`/`confluence_producer.py`/3 others firing clean `exit=0` all day via Task Scheduler yet never writing fresh content, while identical manual replication of the SAME invocation chain works instantly) strongly suggests a real off-desktop-specific behavior difference exists SOMEWHERE in this chain, just not in the file this fire inspected. Needs either: (a) live instrumentation -- add a temp diagnostic print of `os.environ` / session state to one producer, wait for a real unattended (locked-screen) scheduled fire, read the result -- or (b) a deeper trace of `run_exe_hidden.vbs` and any Windows-side session-0-isolation quirk for `wscript.exe`-launched `pythonw.exe` children. Concrete enough to hand a fresh session a running start, not a blind "look into this". :: depends:none :: status:pending

### T-AUTOPSY-H-2026-08-11-entry-spike MED â€” autopsy hypothesis: paying_the_signal_spike

**Claim:** entries fill materially above the signal-minute low -- the marketable ask+buffer buys the local premium spike (defect #2). **Evidence:** `{"median_paid_above_min_low": 0.082, "n": 30}` (analysis/autopsies/2026-08-11.md).
**Action:** entry_manager shadow (T-W5): log limit-below/patience counterfactual fills next to real entries for 3+ sessions :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-08-11-left-on-table MED â€” autopsy hypothesis: exit_shape_dominated

**Claim:** a fixed counterfactual shape beats the shipped exits by more than 2x the window's net P&L -- the exit shape, not the signal, is the bottleneck. **Evidence:** `{"sum_stop_cost": 7490.1, "window_net_pnl": -1946.0, "n_dominated": 20, "window_n": 30}` (analysis/autopsies/2026-08-11.md).
**Action:** STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates Â· enumerate levers beyond exit shape per markdown/trading-knowledge/GENERATIVE-LENS.md (DTE / spread / strike / sizing) :: depends:none :: status:proposed

### T-CONVICTION-TL-2026-08-18 HIGH â€” conviction cannot see trendlines; it gates sizing re-arm

**Claim:** the entry-quality gate that `min_contracts_equity_scaled` re-arm waits on scored the 08-17 winner 0/8 (no trendline component; C4 anti-momentum) â€” it can never validate as built, so sizing stays frozen at min_contracts forever. **Evidence:** first post-fix day 58/58 would_block incl. the +$360 winner; outcome join WOULD_BLOCK=+$360/WOULD_ALLOW=none (analysis/conviction/CONVICTION-VERDICT-2026-08-12.md Â§2026-08-18, analysis/entry-quality/conviction-shadow-report.json).
**Action:** implement shadow-only `conviction_tl` variant per the design note (C-trendline 0-2pts from line metadata + lane-aware C4) logged side-by-side in the same decision row; paired outcome join decides; OP-11 gates before any arming :: depends:none :: status:proposed

### T-JQL-CLASSIFIER-2026-08-18 LOW â€” j-question-ledger intent classifier counts audit prompts as J questions

**Claim:** the j-mind-check hook's intent classifier logged free-model-audit blind-reanswer prompts (machine-generated, contain "running"-adjacent phrasing) as `is_running` J-questions â€” 43 logged, most machine traffic â€” so the "repeated question = missing instrument" escalation math is inflated and untrustworthy. **Evidence:** automation/state/j-question-ledger.jsonl rows 2026-08-14/16 19:00-19:02 are verbatim audit-harness prompts ("You are being asked to give an INDEPENDENT, BLIND answer for an audit"), not J.
**Action:** locate the hook script (fired as `[j-mind-check]` on UserPromptSubmit; not under repo .claude/ or ~/.claude root â€” check settings hook config), exclude non-interactive/machine sources (audit task_ids, subagent prompts) from the ledger, backfill-tag the polluted rows, guard :: depends:none :: status:proposed

### WEEKLY-OPTIONS-BUILD HIGH â€” Phase 0 build of the weekly-options second lane (J-directed 2026-08-18)

**Claim:** J directed the 0DTE-shop â†’ full-options-shop expansion (weekly expirations on GLD/QQQ first, then NVDA post-8/26, TSLA/AAPL). Design is COMPLETE and doctrine-recorded; the build is specced, autonomous, and $0 recurring. **Evidence:** `markdown/planning/WEEKLY-OPTIONS-PROGRAM.md` (Â§7 build order, Â§8 pre-registered gates/kills, frozen 2026-08-18) + `analysis/deep-research/OPTIONS-SHOP-EXPANSION-2026-08-18.md` (5-agent research + live broker probes).
**Action:** execute program doc Â§7 Phase 0 in order: (1) `automation/state/weekly/params.json` per Â§4 v1 rules; (2) generalize `fleet_broker.py` SPY-prefix helpers + 4 duplicate sites (`atomic_bracket_guard.py:84` incl. the `symbol[9]` OCC-index fix, `entry_location_shadow.py:99`, `fast_path_executor.py:359,369`, `trade_today_watcher.py:81`) + `strike_selection.py` strike-increment fix, each with RED-proofed guard tests; (3) `weekly_expiry_selector` reading the LIVE chain (test the NVDA-missing-8/26 case); (4) sector-heat scanner â†’ `analysis/sector-heat/{date}.json`; (5) `weekly_core` SHADOW mode for GLD+QQQ â†’ `automation/state/weekly/shadow-ledger.jsonl`; (6) `weekly-1` arm into `accounts.json` as pending_build AFTER a blast-radius check that fleet_executor skips non-active arms. Phase 1 (J, blocking): create the paper account + key per Â§7 step 8 â€” surface the ask on the REVOKE surface when Phase 0 lands. NEVER route weekly symbols through the SPY core accounts (flat-check blindness, program doc Â§3). :: depends:none :: status:done

**CLOSED 2026-08-19 ~01:xx ET (conductor AFTERHOURS, loop-closing pass â€” not new build).** Re-derived state before trusting the stale `status:pending` label (OP-33): an unattributed overnight session (J's own standing authorization, 2026-08-18 ~21:44 ET, "build all night...put yourself into a loop and get it done") already executed ALL of Phase 0 AND ran well past it â€” full night-run ledger at `markdown/planning/WEEKLY-OPTIONS-PROGRAM.md` Â§9b, 9 real commits (`e4f949ca b89e5f6c 68c0e239 a346f111 031094a7 8992d743 0d7fe5a1 8295f376 1136bed0 36827ccd`), verified to exist via `git cat-file -t` before trusting the claim. Outcome: the which-Friday expiry experiment **RAN** (684 real positions, 862K option bars, frozen pre-registration) and the signal **FAILED the random-entry null on every arm** (âˆ’8% to âˆ’14% mean return) â€” nothing ships, no account created, `weekly-1` deliberately NOT yet added to `accounts.json` (the program doc's own step 6 was reordered â€” correctly â€” behind the kill-gate result; adding a pending_build arm for a killed signal would be inventory, not progress). Phase-9 scheduled-task wiring explicitly DEFERRED with a stated reason (would wire a proven-losing trigger â€” new C7 silent-failure surface). Full J-facing morning brief already written + committed: `analysis/daily-brief/2026-08-19-WEEKLY-LANE-MORNING-BRIEF.md` (commit `36827ccd`) â€” names the 4 things needing J (create-account [recommends NOT yet], overnight-trim semantics, GLD cutoff-class confirmation, live money) and 4 ranked next experiments. **This fire's own contribution:** the work was 100% committed but ZERO STATUS.md entries and ZERO Discord/companion pings existed for a 9-commit, 862K-bar overnight program â€” J's primary wake-signal surfaces were silent on it. Closed that gap: this queue entry, one STATUS.md line, and a Discord ping (see below). Also found + logged as a lesson: `gamma_manager`'s free-tier "strategist" role (`analysis/manager/2026-08-18-2253-strategist-weekly-options-build.md`, untracked) fabricated a completion report for this SAME task with fake artifacts/paths/Monte-Carlo numbers that were never written to disk, while the real work was genuinely in flight elsewhere â€” a live illustration of exactly the class OP-32's free-model trust gate exists to catch. Zero trading-path files touched this fire (queue.md + STATUS.md bookkeeping + one lesson-inbox file). Revert: n/a (doc-only bookkeeping, nothing to revert; the underlying 9 commits are each independently revertible per their own messages).

### T-AUTOPSY-H-2026-08-19-left-on-table MED â€” autopsy hypothesis: exit_shape_dominated

**Claim:** a fixed counterfactual shape beats the shipped exits by more than 2x the window's net P&L -- the exit shape, not the signal, is the bottleneck. **Evidence:** `{"sum_stop_cost": 4579.2, "window_net_pnl": -1354.0, "n_dominated": 7, "window_n": 30}` (analysis/autopsies/2026-08-19.md).
**Action:** STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates Â· enumerate levers beyond exit shape per markdown/trading-knowledge/GENERATIVE-LENS.md (DTE / spread / strike / sizing) :: depends:none :: status:proposed

### T-INTENT-PUSH-2026-08-19 HIGH -- 4 of 6 repeated J-intents are PULL_ONLY; delivery is the autonomy blocker

**Claim:** J keeps asking the same six questions not because the machinery is missing but because nothing PUSHES him the answer. Mined `automation/state/j-question-ledger.jsonl` (29 genuine prompts of 52 rows): `is_everything_running` x4, `status_tldr` x3, `new_lane` x3, `edge_review` x2, `todays_theory` x1, `explain_for_me` x1. **Five of six already have complete machinery on disk** (connectivity-gate/preflight-gate/PreopenReadiness, FirmBrief/MorningBrief/STATUS.md, Prospector/Kitchen, TradeAutopsy/WinnerAutopsy, today-bias.json) yet 4 of 6 are delivery_status PULL_ONLY. **Evidence:** `automation/state/worker-registry.json` .j_intents (validated GREEN by `python setup/scripts/worker_registry.py --check`), full analysis `analysis/deep-research/AGENT-ORCHESTRATION-2026-08-19.md` Part 2.
**Action:** do NOT add worker agents (research-backed kill: 5 of 6 problems are already solved on disk; a new agent adds 3-10x tokens + a telephone-game hop). Instead wire the existing $0 outputs to a push surface -- one pre-open readiness line and one EOD edge line through the already-built Discord outbox / companion bus -- then flip those intents to delivery_status PUSH in the registry and let `--intents` prove it :: depends:none :: status:proposed

### T-EXPLAIN-OWNER-2026-08-19 MED -- `explain_for_me` is the one J-intent with no owner and no machinery

**Claim:** every other repeated J-intent has an owning worker; `explain_for_me` ("break this down for me, how does this help me, what exactly do you recommend I do") has neither owner nor machinery. It is the translation layer from machine output to J-actionable meaning. **Evidence:** `automation/state/worker-registry.json` .j_intents.explain_for_me (owner UNOWNED, machinery [], delivery NONE); ledger prompt 2026-07-08.
**Action:** decide OWNER before building anything -- the cheap answer is a register/format applied by whoever already writes the brief (analyst for EOD, coach for status), not a new agent. Re-read `markdown/planning/GAMMA-WORKER.md` "narrative register v1.1" first: that layer was already designed and partly shipped, so this is likely a re-wire, not a build :: depends:none :: status:proposed

### T-NUMERIC-FABRICATION-2026-08-19 MED -- the anti-fabrication gate proves files exist, not that numbers are real

**Claim:** `worker_output_verify.py` closes the artifact half of the free-model trust gap (12/690 reports caught) but explicitly does NOT verify numeric claims -- the 08-18 scar report also carried invented Monte-Carlo figures ("Max loss = 0.07%", "100% pass rate") that no deterministic check touches. **Evidence:** the tool's own WHAT IT DOES NOT CHECK docstring; `analysis/manager/2026-08-18-2253-strategist-weekly-options-build.md`.
**Action:** narrow scope first -- most fabricated numbers in this rig cite a named artifact, so the highest-ROI next gate is "a metric asserted alongside a file path must be re-derivable from that file", not general numeric verification. Prototype against the 12 known-fabricated reports as the labelled positive set and the 40 VERIFIED ones as the negative set :: depends:none :: status:proposed

### T-KALSHI-DEAD-2026-08-20 MED -- the Kalshi lane stopped ticking 10+ days ago and nothing noticed

**Claim:** `automation/state/kalshi/last-tick.json` was last written 2026-08-09 -- 246h / 10.3 days before this was found. The desk was being reported as a healthy shadow lane "progressing toward its per-city bar" because the assessor counted ledger ROWS and never asked whether the lane was RUNNING. A row count measures history, not life. **Evidence:** `desk_allocator.py` now scores it BROKEN(+40) with "kalshi last-tick 246h stale"; `Gamma_KalshiAuto` is registered 18:10 ET daily in SCHEDULED-TASKS.md.
**Action:** diagnose WHY it stopped before re-arming anything -- check `Gamma_KalshiAuto` last run result, `automation/state/kalshi/auto.log` and `tick.log` tails, and whether the 2 shadow-ledger rows are the whole history or a truncation. This is SURFACED, not diagnosed: the fix may be a dead scheduled task, an API change, or a lane that was quietly abandoned. Do not "fix" it by restarting blind :: depends:none :: status:closed
> **CLOSED 2026-08-29 (Fable full review): FALSE POSITIVE, already diagnosed 2026-08-21.** The "stopped ticking" read came from `automation/state/kalshi/last-tick.json`, which belongs to the RETIRED kalshi-1 direction sub-lane (2 rows total, both 2026-08-09, task never registered -- retired same day it was built). The real lane -- `Gamma_KalshiAuto` weather, 23:08 ET daily -- "ran clean the entire time": `weather-predictions.jsonl` has 133 rows through 2026-08-28, best city n=15/20 scored days toward its frozen bar (20 days AND hit>=45% AND MAE<=1.6F). Fix already shipped in `setup/scripts/desk_allocator.py::assess_prediction_markets` ("SECOND DEFECT FIXED 2026-08-21", lines ~273-296). Nothing to restart. Remaining Kalshi work lives in KALSHI-RTH-LIQUIDITY-RERUN (spread survey) + the J-only API-key step.

### T-COCKPIT-UNEXERCISED-2026-08-20 LOW -- the cockpit's interactive paths have never been driven by J

**Claim:** every view, drawer, the Cmd-K palette and the keyboard nav are verified programmatically (72 guards, live DOM assertions), but nobody has actually double-clicked `LAUNCH-GAMMA-HOME.vbs` or pressed Cmd-K as a human. Built != used. **Evidence:** verification in this session was `javascript_exec` against the rendered DOM in a preview pane, which serves the file from a `data:` URL -- a context that already masked one real routing bug (hash mutation being a no-op).
**Action:** J opens it once and reports anything that misbehaves; specifically worth checking on a real `file://` load: hash deep-links (`#engine`), the `g`-then-key jumps, and whether the 30s age repaint is visible. Any failure here is a guard gap, so fix the guard too, not just the page :: depends:none :: status:proposed

### T-FILTER8-PROVENANCE-2026-08-20 RESOLVED-NULL -- VIX-regime filter gated 89% of a correctly-called trend day, twice running

**Claim:** 2026-08-20 was a clean one-way bear day (768.74 -> 763.04, ribbon+15m BEAR on 772/772 ticks, pre-registered bias BEARISH and 4/4 directionally correct). Filter 8 (VIX regime: not low AND not falling) blocked bear entries on **344 of 386 safe ticks (89%)** with VIX pinned 15.49-16.13 all session. Only 40 ticks -- 12:56 to 15:40 -- had zero bear blockers, and ENTER fired on all 40. At **11:11 bear score hit 9 with filter 8 as the SOLE remaining blocker** at SPY 766.57; SPY went on to 763.04. Same pattern the prior session. **Evidence:** `analysis/eod-deep/eod-deep-2026-08-20.md` sections 3 and 5.
**Action:** do NOT relax the threshold on this narrative -- the counterfactual is unknown and an 11:11 entry could equally have chopped for 90 minutes. Run a CONSTRAINT PROVENANCE AUDIT first (what evidence armed the current threshold, when, and against what n), then a pre-registered A/B on the relaxed variant that must clear OOS + the random-entry null + anchor-no-regression before anything ships :: depends:none :: status:proposed

### T-BOLD-FILLBAR-GATE-2026-08-20 MED -- bold-2 was blocked 16x by an entry gate safe-2 does not have

**Claim:** at 12:56-13:12 safe-2 entered on ENTER_BEAR while bold-2 logged `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` -- "blocked by entry gate require_bearish_fill_bar" -- and only entered 20 minutes later. Both arms won today so this cost nothing, but per doctrine **arms differ by RISK PROFILE (sizing/stops/caps), not by signal access**. **Evidence:** 16 SKIP verdicts in `core-decisions.jsonl` for 2026-08-20, all account=bold.
**Action:** confirm whether `require_bearish_fill_bar` is deliberately bold-only and, if so, record WHERE that was ratified. If it is unintentional divergence, it is the same class as the strike-tier split that produced the 2026-07-18 ATM ship :: depends:none :: status:proposed

### T-CORE-TICK-TIMEOUT-COUNTER-2026-08-20 LOW -- one silent ERROR tick, no counter behind it

**Claim:** `14:40:02 bold verdict=ERROR error="The read operation timed out"` -- one core tick lost, no position at risk, nothing raised. One timeout is noise; a PATTERN of them is a blind engine, and today there is no instrument that would distinguish the two. **Evidence:** single ERROR row in `core-decisions.jsonl` for 2026-08-20.
**Action:** count ERROR verdicts per session into the existing self-check surface and flag only on a threshold (e.g. >3/session or 2 consecutive). Do not alert on one :: depends:none :: status:proposed

### T-TRADE1-LONG-INTO-BEAR-2026-08-20 HIGH -- the only genuine error today: a long into a fully bearish tape

**Claim:** at 10:26 safe-2 bought 3x SPY260820C00767000 @1.05 and exited 59 seconds later @0.87 (-$54) -- the ONLY long of the session. At that moment ribbon was BEAR, htf_15m was BEAR (both were BEAR on 772/772 ticks all day), and the pre-registered bias written before the open was BEARISH. **Every piece of context the engine had already recorded contradicted the trade.** Unlike the filter-8 question (now RESOLVED-NULL: extending the bypass loses money, measured twice), this is not a gate-tuning question -- it is an entry that should not have been generated. **Evidence:** `analysis/eod-deep/eod-deep-2026-08-20.md` section 4 trade 1; `core-decisions.jsonl` 2026-08-20 shows bull_score peaking at 8-9 in the 10:15-10:30 window while bear context was unanimous.
**Action:** trace WHICH bull trigger fired at 10:26 and why the bull path was eligible at all while ribbon+htf were both BEAR. Do NOT add a "no longs on bear days" rule from one -$54 sample -- first measure how often the bull path fires against a unanimous-bear context across the population, and what that cohort earns. If it is net-negative at n>=20, THAT is the pre-registered A/B :: depends:none :: status:proposed

### T-GATE8-WORKPACKAGE-2026-08-20 PARTIALLY-RESOLVED -- the one-gate problem: full work package for an Opus worker

**Claim:** J (on Fable): "I am failing to understand why we can see a setup all day and one gate prevents us from getting in." Mechanism chain answered: binary entry x one shared signal (r=0.846) x one relief valve (trendline-only bypass) x gate 8 being a VIX proxy that inverts on calm downtrends -- single point of failure by construction. Every MEASURED relaxation (bypass extend/remove, rung-7/8 ladder, score9+confluence subset) loses on recent data, including -$345 on 2026-08-20 itself (ladder shadow). The genuinely untested cell: score 9 missing EXACTLY blocker [8] with everything else clean -- no prior study stratified by WHICH blocker was missing. **Evidence + full matrices:** `markdown/planning/OPUS-WORKER-HANDOFF-2026-08-20-GATE8.md` (T0 data authority, T1 gate-8 provenance, T2 blocker-stratified re-cut of LADDER-FULLHIST, T3 gate-8 isolation A/B incl. the EXISTING vix_soft_mode flag, T4 bypass third cell trendline_present, T5 exit-survival counterfactual, T6 ladder-ledger dedupe + revalidation clock).
**Action:** run T0/T1/T2 first (T2 is a re-cut of existing replay data, hours not days); T3 only if T2's pre-registered kill criterion passes; pre-reg everything before the first run per the G2 pattern :: depends:none :: status:proposed

### T-LADDER-LEDGER-DUPES-2026-08-20 MED -- ladder shadow ledger double-counts; raw cumulative inflated ~6x

**Claim:** `analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl` contains duplicate tallies (2026-08-07 appears ~8x, 08-13 twice). Raw cumulative added_pnl reads -$21,735; deduped on (date,arm) keeping latest it is ~-$3,380 rung-7 / ~-$3,235 rung-8. The DIRECTION of the verdict is unchanged (8 of 9 live days negative) but any consumer reading the raw file gets a 6x-inflated number. Also `binary_day_pnl` (530.4, risky-3, 08-20) does not reconcile with fills-ledger FIFO (+370 gross) -- accounting scopes need naming. **Evidence:** the ledger itself; dedupe computed 2026-08-20 evening.
**Action:** idempotency key (date+arm+rung, latest wins) on the tally writer; name the binary_day_pnl scope; C7 class -- a shadow whose own bookkeeping is wrong cannot gate anything :: depends:none :: status:proposed

### T-OPEN-TICK-STALE-QUOTE-2026-08-20 HIGH -- the engine opens the session on a ~3h-stale premarket quote, undetected

**Claim:** on 2026-08-20 the first SIX core ticks (09:30:00-09:35) reported spy=768.74 then 769.09 while the last CLOSED 5m bar was 765.94 -- a drift of **+$2.80 to +$3.15**. 768.74 is the **06:35 premarket bar's close**, i.e. a quote ~3 hours old. `blind=False` on every one of those ticks: the never-blind beacon did NOT detect it. Bull score read 9/6 through the stale window and dropped to 8/6 the tick it corrected. From 09:36 the feed matches the last closed bar to the cent (median error 1.5c across the day). **Evidence:** `analysis/recommendations/GATE8-T0-T2-RESULTS-2026-08-20.md` section T0; `automation/state/core-decisions.jsonl` 2026-08-20 ticks 09:30-09:43.
**Action:** no trade resulted today, but 09:30-09:35 is exactly the gap-and-go window and there is a -$1,569 stale-level scar on record (2026-08-14). Add a FRESHNESS assertion to the tick path: if the quote's source bar timestamp is more than 2 bars behind the clock, set blind=True rather than trading on it. Then RED-proof it by replaying 08-20's open. This is a C7 silent-failure class -- the danger is not the staleness, it is that nothing flagged it :: depends:none :: status:proposed

### T-AUTOPSY-H-2026-08-24-entry-spike MED â€” autopsy hypothesis: paying_the_signal_spike

**Claim:** entries fill materially above the signal-minute low -- the marketable ask+buffer buys the local premium spike (defect #2). **Evidence:** `{"median_paid_above_min_low": 0.097, "n": 30}` (analysis/autopsies/2026-08-24.md).
**Action:** entry_manager shadow (T-W5): log limit-below/patience counterfactual fills next to real entries for 3+ sessions :: depends:none :: status:proposed

## 2026-08-26 â€” three items from the 08-26 session review

### [HIGH] ENTRY-FILL-STALENESS â€” measure, do not fix yet
safe-2 reached ENTER_BULL 14:56:03 (bull 11/11), placed `limit buy 3 SPY260826C00766000 @1.43`,
**filled_qty 0**, cancelled 14:59:05. safe-3 filled the identical contract @1.50 and made +$39.
`fleet_broker.marketable_limit_price` = `ask + buffer` off a placement-time quote; the ask ran
past 1.43 before the order reached the book, so a marketable limit arrived non-marketable.
Adversely selected by construction: only fails to cross when price moves away â€” fills losers,
misses winners. 08-25 same account filled a loser at 0.70 vs safe-3's 0.68; 08-26 missed a
winner entirely.
**n=1 in live history** (`SKIP_ORDER_STILL_OPEN_AFTER_CANCEL` has fired once, ever, today).
NOT evidence of a systematic leak. DO NOT tune the buffer on one observation.
TASK: (a) revive `shadow_entry_actuator.py` -> `entry-shadow.jsonl`, dark since 2026-07-06
(98 rows) â€” it is the instrument built for exactly this question; (b) instrument
signal-quote -> placement-quote drift on every entry; (c) revisit only at n>=15.

### [HIGH] GATE-REVALIDATE-CONF-LVL-REC-AFTERNOON
`block_conf_lvl_rec_afternoon` skipped bold-2 **20 consecutive ticks** 14:56-15:55 ET, every one
`bull_score 11` (max) with `level_reclaim + confluence`, SPY 766.49 -> 767.12. The unblocked
lane traded the same signal green. **20 of the gate's 84 lifetime firings (24%) were today.**
`gate_expiry_check` grades it `evidence_age=68d`.
Per J 2026-07-31 (recency > aggregate; every armed gate needs a revalidation clock) this is the
`block_elite_bull` shape. TASK: pre-registered A/B on the recent window before any disarm.
A gate comes off on evidence, never on one day's regret.

### [MED] EOD-DEEPDIVE-SILENT-SUCCESS (C7)
`Gamma_EodDeepDive` fired 16:30 ET with LastTaskResult=0 but wrote no dated output â€”
`analysis/eod-deep/` still ends at 2026-08-21. Exit code is not evidence of work.
TASK: make `run-eod-deep-dive.ps1` fail loud when it produces no dated artifact.

### [CRITICAL] ZONE-ENTRY-BLIND-SPOT â€” the bull vocabulary cannot express a support bounce
2026-08-26. J read the 15m by eye and called "double bottom call entry around 12:45, right off
that 763 level." **Actual day low: 763.99 at 12:46 ET â€” one minute out.**

At 12:45 the engine had `ribbon=BEAR, bull=7, bull_triggers=[]` and
`bear_triggers=[level_rejection, confluence, trendline_rejection]`. At the exact bottom every
bull input was dark and every bear input lit. The engine read the demand-zone bounce INVERTED.

Cost: available move low->high +3.26 pts. Engine entered 766.49 @14:56 = **+2.50 pts above the
low, 130 min late**, with only 0.76 pts left. Captured +0.36 pts = **11% of the move**. That is
why a 43-minute hold made $39 -- the entry was not too early, it was structurally LATE.

ROOT CAUSE (`backtest/lib/filters.py:908`):
    detect_level_reclaim -> `if bar["low"] < lvl and bar["close"] > lvl`   # SINGLE BAR
The only bullish level trigger requires ONE bar to break BELOW a level and close back above.
Consequences: (a) a bounce that RESPECTS support never fires -- no bar dips under the level;
(b) a MULTI-BAR double bottom never fires -- the detector is single-bar; (c) the ribbon is a
lagging MA stack and was BEAR at the low. The engine can only go long AFTER price has climbed
back above a level, i.e. after the move.

Same blind-spot CLASS as the trendline lane (entry path reads pivot HIGHS, so ascending support
is invisible by construction). Same doctrine target: J's philosophy is zone -> return ->
STRUCTURE SHIFT AT THE ZONE. There is no "at the zone" trigger in the engine at all.
Lesson theme C16 (multi-bar reversal vs single-bar continuation) predicted this.

DO NOT WRITE A DETECTOR YET. n=1 day; J's eye is a hypothesis with one excellent data point,
not a measured edge. TASK, in order:
1. Harvest J-style demand-zone bounces across history (multi-bar reversal at a named level,
   structure shift confirming) -- a LABELLING pass, no trading logic.
2. Pre-register the null FIRST: does "structure shift at the zone" beat "reclaim after the
   move" on REAL FILLS, net of the extra losers that entering earlier at a zone must produce?
   The obvious failure mode is catching falling knives -- the null must be able to kill it.
3. Only on a pass: shadow lane, then arm. Never straight to the entry path.
Related dead ends to read first: MULTI-LANE-STAGE-A-VERDICT-2026-08-20 (level+structure-shift
family already KILLED twice) -- this proposal MUST explain why it differs or it is dead on arrival.

### T-AUTOPSY-H-2026-08-27-left-on-table MED â€” autopsy hypothesis: exit_shape_dominated

**Claim:** a fixed counterfactual shape beats the shipped exits by more than 2x the window's net P&L -- the exit shape, not the signal, is the bottleneck. **Evidence:** `{"sum_stop_cost": 4525.5, "window_net_pnl": 1554.0, "n_dominated": 11, "window_n": 30}` (analysis/autopsies/2026-08-27.md).
**Action:** STOP-A sign-off -> T-W7 confirmatory on the frozen v2 candidates Â· enumerate levers beyond exit shape per markdown/trading-knowledge/GENERATIVE-LENS.md (DTE / spread / strike / sizing) :: depends:none :: status:proposed

- [ ] ESCALATION (worker_fabrication) [5b354718027914a9] (seen 3x since 2026-08-20) â€” critic claimed artifacts that do not exist for 'critique_gap_and_go_weakest_assumption': backtest/gap_and_go_config.json _(gamma_manager 2026-08-29 05:53 ET)_

- [ ] ESCALATION (manager_flagged) [71b11ddf50de3d1b] — Ideate ONE concrete new variant of the l: Pending queue.md tail item #1-3 explicitly demand a level-rejection pullback variant that passes the structure-shift null. Two prior kills make this a genuine _(gamma_manager 2026-08-30 05:53 ET)_

### T-AUTOPSY-H-2026-09-01-entry-spike MED — autopsy hypothesis: paying_the_signal_spike

**Claim:** entries fill materially above the signal-minute low -- the marketable ask+buffer buys the local premium spike (defect #2). **Evidence:** `{"median_paid_above_min_low": 0.105, "n": 30}` (analysis/autopsies/2026-09-01.md).
**Action:** entry_manager shadow (T-W5): log limit-below/patience counterfactual fills next to real entries for 3+ sessions :: depends:none :: status:proposed

### Filed 2026-09-02 (Opus, scheduled-task staleness root-cause)

- [ ] TASK-SCHEDULER-OPERATIONAL-LOG-DISABLED (MED, J-ONLY one-liner, filed 2026-09-02) :: the
  `Microsoft-Windows-TaskScheduler/Operational` log is DISABLED on this box (`IsEnabled=False`,
  zero records), so ~150 Gamma tasks have NO scheduler-side history. Every "did it actually fire?"
  question must be reconstructed from artifacts and `run-cmd-hidden-*.log`, which is exactly why
  the GuardsFull darkness took a differential to diagnose rather than one log query. Enabling it is
  a single command and is diagnostic-only (more audit trail, not less). NOT done autonomously: it
  is a machine-wide OS setting outside the repo and not git-revertible, so it is J's call. Command:
  `wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true` (elevated).
  :: depends:J :: status:filed

- [ ] RULE-AUDIT-COVERAGE-GAPS (MED, filed 2026-09-02 from the first rule-break audit run) :: the new
  auditor covers rules 1-6 and explicitly cannot check four. Each is a real gap, not a permanent one:
  **R7 PDT** needs the broker's rolling 5-business-day day-trade count (the per-row `day_trades` field
  is not the same number -- one fleet row shows `day_trades: 0` next to `day_trades_true: 5`); **R8
  journal-every-trade** needs a verified fill -> `journal/trades.csv` join key, and a wrong join would
  manufacture false breaks on the gate's own ledger, so it was left unchecked rather than guessed;
  **R9 no-mid-session-rule-changes** needs params-file history during RTH, which is not retained --
  cheapest fix is a daily hash of the frozen trading-path files stamped at the open and the close;
  **R10** is not mechanically checkable by construction. Also note `RULE_2` is core-arms-only (76 of
  495 entries) because fleet rows do not record `trigger_bar_et` -- adding that field to the fleet
  ENTER row would take anticipation-entry coverage from 15% to ~100% of entries.
  :: depends:none :: status:filed
  **PARTIAL 03:41 ET 2026-09-03 (Sonnet, Fable-verified 49 passed):** `rule_break_audit.py --live-r7-r8 --r8-date` (additive; default run byte-identical and never touches the broker, pinned). **R7:** Alpaca's account payload carries NEITHER `pattern_day_trader` NOR `daytrade_count` on any of the 5 reachable arms (re-confirmed live 09-03; matches pdt_tracker's 08-18 finding) -- so the proposed break condition has no field to read; ships as per-arm OBSERVATION (equity, intraday_adjustments, `break_checkable:false`), no fabricated check. **R8:** broker closed orders (ET-date filtered locally) joined to `journal/trades.csv` legs by (account, OCC symbol, side, qty, +/-120s, +/-$0.02) with a qty-summing split-fill fallback: **2026-09-02 24/24 journaled (100%), 2026-08-27 29/29 (100%)** -- the only 'misses' were one qty=5 fill journaled as 1+4 rows. Ships as OBSERVATION (match rate), not an auto-break, per the item's own warning. R9/R10 stay NOT_CHECKED with the exact missing artifacts named (RTH open/close hash of frozen files; retired veto ledger shape). Remaining: R9 needs the hash producer (post-freeze design). :: status:partial

- [ ] FULLHIST-ANCHOR-DRIFTED-190-TO-189 (MED, stale anchor vs real regression, NOT
  re-baselined, filed 2026-09-02) :: `test_structure_shift_cascade_ab.py::TestBaselineAnchor
  Reproduction::test_control_prefix_reproduces_stored_scorecard` asserts the control replay
  reproduces the stored `engine-fullhist-replay-2026-07-23` scorecard as a strict prefix: 190
  trades <= 2026-07-22. It now yields **189**, deterministically (reproduced 3x). SPY/VIX source
  CSVs are untouched since 2026-07-22 and no option CSV in `backtest/data/options/` was modified;
  no frozen trading-path file has changed. **The diff is not a simple omission:** vs the stored
  scorecard, three dates are GONE (2025-07-17, 2025-12-11, 2026-01-27) and one is NEW
  (2025-12-03). A missing OPRA cache file can only REMOVE trades, so an added trade means
  SELECTION LOGIC moved, not data availability. **Leading hypothesis, NOT proven:** `4249d95e`
  (deterministic LevelState resolution) + `30e51b9f` (2026-08-23, its adversarial-review
  follow-ups) changed which levels resolve -- 30e51b9f's own message states a NaN-priced
  LevelState "was ADMITTED where the old linear scan excluded it" and that this was fixed
  fail-closed, which is exactly a change in what triggers. If so the anchor is STALE (the engine
  legitimately moved under a 07-23 snapshot), not broken. **DELIBERATELY NOT RE-BASELINED to
  189.** Re-pointing an anchor at whatever the code currently produces is the metric-picking this
  repo's own backtesting playbook exists to prevent -- it converts a regression detector into a
  tautology. The re-baseline must NAME the commit that moved the number and show the four
  changed dates are explained by it; until then the test stays RED and honest. Cheapest decisive
  experiment: re-run the control with the pre-4249d95e resolver in an ISOLATED WORKTREE (never
  a checkout in the shared tree -- C34) and check whether the prefix returns to 190.
  :: depends:none :: status:filed

- [ ] LEVEL-MEMORY-LIVE-MERGE-UNVALIDATED (MED, live behaviour on unreproducible evidence,
  FROZEN-BLOCKED until 10-30, filed 2026-09-02) :: `automation/state/params.json` carries
  `level_memory_live_merge: true`, and `setup/scripts/refresh_levels_intraday.py:700` really does
  UNION the multi-day memory map into the live level feed on every intraday refresh -- so this is
  a behaviour the engine reasons from, not a dormant knob. Its ONLY evidence is
  `analysis/recommendations/level-memory-wire.json` (CONTROL 28 / TREATMENT 26, n_effect=3,
  -$489.50, `NEGATIVE_INSUFFICIENT_N`, "leave the flag ON -- insufficient n for a kill").
  **That scorecard cannot be regenerated by any code in this repo at any commit:** the
  `memory_levels_by_day` hook its runner requires has never existed in `levels.py` or
  `orchestrator.py` (`git log -S` over all history), and the commit that claims to have added it
  (`e84c062f`) touches six files, none of them engine code. The control does not reproduce
  either -- 28 trades in July, 36 today on the same window. **And the frozen study measured a
  formula production abandoned on 2026-07-27** (side-blind nearest-6, replaced by per-side cap 3
  after J flagged that side-blind selection gave an all-resistance set with zero supports).
  **NOT turned off, deliberately:** `params.json` is frozen to 2026-10-30, and the honest state
  is UNMEASURED, not refuted -- "we cannot reproduce the evidence" is not a verdict that the
  behaviour is harmful, and acting as if it were would be the same error in the opposite
  direction. **At 10-30, one of two:** (a) write a NEW prereg against the CURRENT per-side
  formula, build the hook additively (default None = byte-identical for every existing caller),
  and run a real A/B; or (b) if nobody will fund the study, turn the flag off on the grounds that
  an unmeasured behaviour should not be live -- but say which of the two was chosen and why.
  Retired prereg + full forensics: `analysis/recommendations/prereg-level-memory-wire-2026-07-15
  .json#reopened_and_corrected_2026_09_02`. Guard:
  `backtest/tests/test_level_memory_wire_provenance_2026_09_02.py`.
  :: depends:none :: status:filed

- [ ] PREREG-BUILD-CLAIMS-ARE-UNFALSIFIABLE-AS-WRITTEN (LOW, monitor design, filed 2026-09-02) ::
  The level-memory prereg carried `build_step_complete: "backtest/lib/levels.py#_detect_from_history
  extended with an ADDITIVE-ONLY 'memory_levels_by_day' kwarg..."` -- a claim that was FALSE, and
  that **a generic "does the claimed build exist?" monitor would still have passed**, because the
  file exists and the function exists; only the KWARG was missing, one level below the claim's
  granularity. Only 2 preregs in `analysis/recommendations/` carry a build-step claim at all, so
  this is not worth a general checker today (n=2, and naive path extraction from prose produced
  false MISSING hits on bare filenames like `refresh_levels_intraday.py`). Worth revisiting if
  the pattern spreads: the fix is not a smarter parser but a STRUCTURED field -- e.g.
  `build_step: {file, symbol, must_contain}` -- so the claim is machine-checkable by construction
  instead of being prose a regex has to guess at. :: depends:none :: status:filed
  **PARKED 03:43 ET 2026-09-03 (Fable decision):** n=2 preregs carry a build-step claim; a checker is not worth building until the pattern spreads. Standing rule instead: any NEW prereg that claims a build step must carry a structured `build_step: {file, symbol, must_contain}` field (machine-checkable by construction); `prereg_hygiene.py` will flag prose-only build claims when it next touches that schema. Re-open when a third prereg carries a build claim. :: status:parked

- [ ] SAFE-2-RETIREMENT-IS-NOT-A-REGISTRY-EDIT (HIGH, ships in the 09-29 bundle, found 2026-09-02
  by the new arm-roster sweep) :: **Setting `safe-2` to `status: retired` in `accounts.json` would
  NOT stop the core engine trading it.** `setup/scripts/heartbeat_core.py` hardcodes its roster as
  `(safe-2, bold-2)` and never reads the registry to decide which accounts to trade. This is the
  same arming asymmetry work-order §2a recorded from the other direction: fleet arms arm via the
  roster's `live` flag, the core pair arms via `GAMMA_CORE_ARMED=1` in `run-heartbeat-core.ps1`
  and carries **no `live` key at all**. So the roster alone can neither arm nor retire a core arm.
  **Consequence for the checkpoint:** safe-2's retirement is a CODE change on
  `safety-bundle-2026-09-29`, not a config tweak, and anyone who retires it by editing the
  registry will believe it is done while the engine keeps trading. **Context measured the same
  day:** 66 modules read `accounts.json` independently and **15 hardcode an arm tuple instead** --
  `risky-3` is still named in nine of them five days after retirement, `safe-1` in four. Canonical
  helper now exists (`automation/state/fleet/arm_roster.py`, semantics lifted from
  `eod_flatten._active_arms` and pinned against it) and the sweep
  (`backtest/tests/test_arm_roster_sweep_2026_09_02.py`) fails on any UNDECLARED static roster, so
  the next retirement cannot be silent. Converting `heartbeat_core`'s own roster is deliberately
  NOT done in the guard -- it is a trading-path change that belongs in the reviewed bundle merge.
  :: depends:none :: status:filed

- [x] FUTURES-PREMARKET-LEVELS-CONSUMER (LOW, lane design, filed 2026-09-03 01:08 ET) :: `Gamma_FuturesPremarket2` now writes MES/MNQ key-levels + today-bias before the open, but `futures_trader_core.py` / `futures_heartbeat_core.py` compute levels internally via `lib.levels._detect_from_history` and read neither file. Decide whether the lane should PREFER the premarket levels, CROSS-CHECK them (log disagreement only), or stay internal. Cross-check-only is the freeze-safe default. :: depends:none :: status:filed
  **DECIDED 03:43 ET 2026-09-03 (Fable):** cross-check only (freeze-safe default); implementation folded into FUTURES-LANE-WIRING-2 (c). :: status:folded
- [ ] RE-ANCHOR-FULLHIST-REPLAY (HIGH, reviewed change, Sunday 09-07 adjudication; filed 2026-09-03 01:15 ET from the first slow-suite run since July) :: `test_structure_shift_cascade_ab.py::TestBaselineAnchorReproduction::test_control_prefix_reproduces_stored_scorecard` FAILS deterministically (3/3 runs): current engine replays **189** trades vs the test's hardcoded **190** / stored JSON **191**. Root cause (investigated, `analysis/harness-fidelity/FULLHIST-ANCHOR-DRIFT-2026-09-03.md`): commit `4249d95e` (2026-08-23, deterministic `resolve_level_state`, a RED-proofed correctness fix) changed `sequence_reclaim` lookups -- 5 trades out, 3 in (2 of the 3 are same-day NOT_FLAT cascade effects). Second finding: the test's literals (190 / $5,064.75) were already stale -- `df0348d9` (08-01) regenerated the JSON to 191 / $4,808.75 and never updated the test. Data files and tonight's commits ruled out. **ACTION (one reviewed change, not tonight):** regenerate `engine-fullhist-replay-2026-07-23.json` with the CURRENT engine AND the `et_frame` (et-v2) timestamp parse (the two-frame winter shift, SPY-BAR-FILE-MIXES-TWO-TIME-FRAMES, touches 67 of the 191 trades), publish the before/after trade diff in the open, update the go-live gate's criterion-1 disclosure numbers, and make the test read `stored['headline']` dynamically. Until then the slow suite carries exactly this 1 known RED and walker/gate disclosures cite an anchor the engine no longer reproduces. :: depends:none :: status:filed

- [x] WALKER-MARKET-STAGE-FILL-ROOT-FIX (HIGH, harness fidelity, GATE-ADJACENT; filed 2026-09-03 01:25 ET from WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY) :: `multileg_exit_walk` priced every market-style exit at the static stop level (see the parent item); the flagged fix moves the PDT anchor ratio 4.09 -> 2.84 but the walker still fails the magnitude criterion (|ratio-1|<=0.40). **Why GATE-ADJACENT:** `whole_engine_null.py`'s N_a/N_b/N_c legs are walker-replayed while P1 is real fills, so a too-negative walker makes every null look worse than it is and the study's PASS (HOME: 'engine P1 +$3,562 beats N_a p95 2,545') is biased in the engine's favour by an unknown amount. The Friday 09-05 reading MUST publish `magnitude_fidelity` beside the verdict (now wired) and be read as 'PASS, walker magnitude FAIL' until this closes. DO: finish the pricing fix (give `ExitAction` a real bar price for structure_stop / ribbon_flip / time_stop, honour fill_mode), re-validate on the 43-row PDT anchor AND the whole-engine V9 anchor until the criterion passes, then flip the flag default in its own commit with before/after numbers for BOTH studies in the open. Do not re-run the prereg RUNs (recency-qty-clamp, runner-finite-tgt, profit-lock-arm-scope) before this lands. :: depends:none :: status:filed
  **PARTIAL 2026-09-03 02:50 ET (Sonnet, Fable-specced):** time_stop now fills at the bar close under the flag; structure_stop/ribbon_flip keep `worst_in`; extending worst_in to the threshold stages (premium_stop, profit_lock_floor, trail, be_stop, runner_target) measured WORSE and was reverted -- the live engine fires the instant a 1-min poll crosses the threshold, so `runner_stop_premium` already models those. PDT anchor 3.90 -> 2.64 (median $31.55), V9-population -1.33 -> -0.24 (median $42): **both still FAIL**. Decomposition: premium_stop $811 of $1,780 abs error (n=22), structure_stop $581 (n=13), trail $388 -- the residual is a TIMING gap (which 5-min bar the live 1-min poll caught), not a pricing gap. **CORRECTION to the item text above:** the whole-engine null's legs use `exit_manager_walk`, whose V9 anchor is ratio 0.645 (criterion PASS, sized to it); flag-on research (`analysis/whole-engine-null/2026-09-02-flagon.json`) moved the nulls in the ENGINE's favour, so the published default is the conservative reading. 95 tests, 3 mutations RED-proofed. NEXT: model the 1-min poll timing for premium_stop (walk the 1-min bars where cached, else disclose) -- then re-validate both anchors; flag default stays False. :: status:partial
  **NEGATIVE RESULT + RESIDUAL NAMED 2026-09-03 03:15 ET (Sonnet, Fable-specced):** a 1-min poll model for the threshold stages (`premium_stop_poll_model`, default False) makes fidelity WORSE on both anchors (PDT 2.64 -> 3.26, V9-pop -0.24 -> -0.44) for a provable reason: the fallback price for those stages IS `runner_stop_premium`, the least-adverse price a downside cross can have, so 'first 1-min close at/through the threshold' can only be equal-or-more adverse, and the walker already over-replays losses. The true residual is DECISION granularity (the 5-min bar decides an exit a live 1-min poll may never have confirmed), i.e. only a 1-min-native walk fixes this walker. **DECISION (Fable):** do not keep patching `multileg_exit_walk`; MIGRATE its dollar-sensitive consumers to `exit_manager_walk`, which passes the magnitude criterion (V9 0.645) and is what the null study and tonight's zone-rejection RUN already use -- filed WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK. Both flags stay False. 35 tests, 3 mutations RED-proofed. :: status:closed-negative
- [ ] BEAR-F8-VIX-FLOOR-COSTING-REPLAY (HIGH, research, freeze-compatible; filed 2026-09-03 01:48 ET from the sole-blocker miner's first live run) :: bear sole-[8] (the 17.3 VIX floor, filters.py) alone refused 106 clustered bear entries across 14 of the last 20 sessions (VIX ~15 all month), while the 2026-08-04 postfix quantification called it $0 / zero events on a 2-session window. The proxy says 44 of 106 cost money; bull sole-[10] refused 78 (28 cost). DO: run `backtest/tools/postfix_gate_costing.py`'s full dollar-costing replay over the 20-session cohort for BOTH flagships once the OPRA cache is free (NOT tonight -- and NOT before WALKER-MARKET-STAGE-FILL-ROOT-FIX clears, since the replay prices exits with the same walker), report with/without best-day, and hand the number to the 10-30 shape menu. The bear side is RED_CONCENTRATED on real fills (n=31, -$1.77/tr), so a floor that refuses bear entries in a calm regime may be SAVING money -- the replay decides, not the count. :: depends:WALKER-MARKET-STAGE-FILL-ROOT-FIX :: status:filed
  **SCOPE RAISED 03:57 ET 2026-09-03 (Fable):** 08-31 and 09-01 were entirely blocker-8 sit-outs (55 + 60 refused high-score ticks, 7 + 12 episodes). Dollars from either walker are still sign-only evidence, so run this as a SIGN-ONLY costing first: for each refused episode take the first refused tick as the hypothetical entry, walk forward on SPY 1-min bars for the engine's actual median hold (from trades-enriched) and report the fraction of episodes where SPY moved >= the engine's median favourable excursion in the PUT direction before moving the median adverse excursion against it; compare against the same statistic on the sessions where blocker 8 was OPEN and the engine did enter. No option pricing, no walker. Spawned. :: status:in_progress
  **SIGN-ONLY RESULT 04:08 ET 2026-09-03 (Sonnet, pre-registered before running; `analysis/recommendations/bear-f8-vix-floor-sign-costing-2026-09-03.{md,json}`, tool `backtest/tools/bear_f8_sign_costing.py`, 10 tests):** correction first -- the miner's '106 events' is 53 distinct episodes double-counted across safe/bold. Walk = engine's median bear hold 24.1 min, MFE 0.62 pts, MAE 0.42 pts, on SPY 5-min bars (no 1-min SPY file; ties resolve ADVERSE). R (refused, n=53): favourable 26.4% CI [0.167, 0.364]; E (entered, n=31): 41.9% CI [0.188, 0.656]; R-E = -0.155 CI [-0.436, +0.090]. VIX strata of R flat (25% vs 28%). **Verdict under the frozen rule: F8_EARNS_ITS_KEEP** (E point estimate above R's CI-upper) -- the VIX floor refused episodes that would have done worse than the ones it let through, directionally consistent with the bear side's RED_CONCENTRATED real-fills read. Caveats (disclosed): 24 of 70 entry candidates failed the decision-row join (their median hold 1 min vs 24 min), so the hold parameter is biased long; no theta/spread/slippage; wide CIs. 10-30 shape-menu input, not a ship proposal; the dollar costing stays blocked on the walker. :: status:partial
  **NOTE 04:12 ET 2026-09-03:** before any 10-30 use, re-read blocker 8's exact rule from `filters.py`/params (09-01 entered bear at VIX ~16, so the report's '> 17.30 AND rising' is not the whole gate); the sign-only populations above were built from the recorded `bear_blockers==[8]` rows, so they are unaffected by the wording, but the interpretation is.
  **BLOCKER 8 AS CODED 04:30 ET 2026-09-03 (Fable, read from `backtest/lib/filters.py:1671-1690`):** bear filter 8 passes only when VIX_now > VIX_BEAR_THRESHOLD (17.30) AND `vix_direction(now, prior) == rising` AND VIX_now <= VIX_HARD_CAP_BEAR (23) AND (if VIX_DECLINING_REQUIRED_BEAR) 5d-MA < 20d-MA; the `vix_entry_thresholds` block in params.json is VESTIGIAL (its own doc says so). Two release valves exist per evaluation: `vix_soft_mode` (filter 8 becomes a -1 score demerit instead of a block) and `allow_one_blocker` (setup passes with one non-structural blocker). 09-01's 13 ENTER_BEAR verdicts at VIX ~16 must have gone through one of those valves (or the RANK-28 BEARISH_REVERSAL bypass) -- UNVERIFIED which; the decision rows for those entries will say. The bull mirror is `VIX < 17.20 OR falling`. Saturday item 9 quotes THIS, not the report.

- [ ] FLEET-EXIT-STATE-SAVE-PER-SYMBOL (HIGH, kill-type risk reduction, SHIP IN THE 09-29 SAFETY BUNDLE; filed 2026-09-03 01:52 ET from the FLEET-PATH-AUDIT residual (3) trace) :: `exit_actuator.py` calls `save_states` ONCE after the per-symbol loop (~798-799); a kill between a broker-accepted TP1 `market_sell` and that write (the task's own 2-min ExecutionTimeLimit or `_shared.ps1`'s >5-min reaper are realistic triggers) leaves `tp1_filled=False` on disk while broker qty already moved. Traced live-equivalent (pinned test): next tick fires a second 'tp1' SELL_PARTIAL on the runner's only contract (mislabeled, skips runner management) or re-checks the original -20% stop instead of the BE ratchet. FIX (branch `safety-bundle-2026-09-29`, own commit): per-symbol `save_states()` immediately after each broker-accepted sell inside the loop; proof test = same harness, on-disk record shows `tp1_filled=True` for the sold symbol after the simulated kill. Guard + RED-proof + one-line revert like the other bundle components. :: depends:none :: status:filed

- [ ] WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK (HIGH, harness fidelity, GATE-ADJACENT; filed 2026-09-03 03:15 ET, supersedes the multileg fix path) :: `multileg_exit_walk` cannot reach the magnitude criterion without a 1-min-native rewrite (see WALKER-MARKET-STAGE-FILL-ROOT-FIX's negative result); `exit_manager_walk` (via `structure_stop_study.replay_structure_aware` -> the live `exit_manager.plan_exit_actions`, per bar) sits at V9 ratio 0.645 / median $15 and is what the whole-engine null and the zone-rejection RUN use. DO: port `pdt_blocked_counterfactual.py` and the three outstanding prereg RUN harnesses (recency-qty-clamp -> `multileg_exit_walk.py` calibration v5, runner-finite-tgt, profit-lock-arm-scope) plus `directional_gate_battery.py` onto `exit_manager_walk`, re-validate each harness on its anchor with `walker_magnitude_fidelity` BEFORE reading any verdict, then re-run the PDT counterfactual (its FAIL_PDT_STAYS_AS_IS should be re-read on trustworthy dollars) and unblock BEAR-F8-VIX-FLOOR-COSTING-REPLAY. Where a study's prereg names `multileg_exit_walk` by contract, record the harness swap as a disclosed deviation with the fidelity numbers side by side. :: depends:none :: status:filed
  **PARTIAL 2026-09-03 03:22 ET (Sonnet port, Fable read) -- FINDING CHANGES THE PLAN:** `pdt_blocked_counterfactual.py` now takes `--walker {multileg,exit_manager}` (default multileg, dispatch pinned byte-identical; published 09-02 artifact untouched, `git status` clean). On the SAME 43-row engine-attributed anchor the two walkers give: multileg ratio 4.09 / median $32.40 FAIL; exit_manager ratio **2.42** / median $30.00 **FAIL** (excess halves, still 3.5x outside |ratio-1|<=0.40). So exit_manager_walk is NOT a clean pass either -- it reads 0.645 (replay 35% SMALL) on the V9 121-row population and 2.42 (replay 2.4x LARGE) on the PDT anchor: opposite-sign bias on two anchors means NEITHER walker's dollar magnitude is anchor-independent; sign agreement (95%) is the only fidelity either has earned. Per-stage decomposition: stage_agree n=30 median err $26 (pricing), stage_disagree n=13 carries 52.5% of abs error (wrong exit EVENT). The counterfactual halted at the gate by design (no G1-G4, no new file). 19 new tests + 78 passed in the sibling suites; 3 mutations RED-proofed. **Plan change:** do NOT port the other three RUNs or the battery until the stage_disagree residual is diagnosed (which exit event the live exit_manager took vs the replay -- likely the chandelier/ribbon decision on a 5-min bar vs the live 1-min poll); filed as WALKER-STAGE-DISAGREE-RESIDUAL below. Until then every replayed dollar figure from either walker is SIGN-ONLY evidence and the work-order §2b disclosure is corrected to say so. :: status:partial
  **NOTE 04:43 ET 2026-09-03 (Fable):** still blocked. The full-population anchor clears only by cancellation (see WALKER-REANCHOR result); migration is decided PER ARM once WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM names the misfire. safe-2 alone (0.96) would already qualify if a consumer is scoped to safe-2 rows only -- allowed as an explicitly scoped exception, disclosed.

- [ ] WALKER-POLL-FAITHFUL-REPLAY (HIGH, harness fidelity, GATE-ADJACENT; filed 2026-09-03 04:57 ET; Sunday-class build, cache single-reader) :: Build `exit_manager_walk` mode `poll_faithful=True`: for each trade, the structure-stop / chandelier / ribbon checks are evaluated ONLY at the timestamps where that arm actually ticked (rows for the arm+date in `core-decisions.jsonl` for core arms and `automation/state/fleet/<arm>/decisions.jsonl` for fleet arms, using each row's `trigger_bar_et` and recorded spot), and for fleet arms the check is skipped on ticks whose shared-signal age exceeded `SIGNAL_MAX_AGE_SEC` (mirror `fleet_live.py:938`); premium-threshold stages keep the 1-min bar walk. Re-score the 223-row full population PER ARM at both slippage settings with the criterion unchanged; the expected signature if the mechanism is right: the 14 TIMING rows flip to agree, bold-2 / risky-1 / safe-3 ratios move toward 1 with safe-2 unchanged. If it clears per arm, WALKER-CONSUMERS migrates; if not, the residual is named again. :: depends:none :: status:filed

- [ ] FLEET-SIGNAL-UNREADABLE-WITH-POSITION (HIGH, live-behaviour, bundle candidate 09-29 after verification; filed 2026-09-03 06:02 ET) :: On fleet arms the shared-signal file is sometimes UNREADABLE (missing/corrupt, `signal_status=signal_unreadable`) and that collapses `last_closed_5m_close` to None exactly like the stale case -- the structure stop is silently not evaluated on that tick. Unlike the stale case this DOES coincide with open positions: 08-25..09-02 risky-1 18 of 38 unreadable ticks and safe-3 6 of 38 had a position open. VERIFY (read-only, same extractor `backtest/tools/fleet_stale_signal_skip_extract.py` extended to `signal_unreadable`): (1) root cause of unreadability (writer/reader race on `build_shared_signal`'s output? partial write? -- quote the reader's exception text), (2) join to trades-enriched: any structure_stop exit on those arms preceded by an unreadable tick with the position open, and how late it fired vs the rule, (3) frequency per session. If any exit was delayed: kill-type fix for the bundle = atomic write (tmp + rename) on the signal writer AND, on the reader, fall back to the arm's own last closed 5-min bar for the structure check when the shared signal is unreadable; guard test + RED-proof + revert line. If no exit was delayed: ship the atomic-write half anyway as hygiene (writer is `build_shared_signal.py` -- FROZEN until 09-29, so bundle) and log loudly. :: depends:none :: status:filed **VERIFIED 18:47 ET 2026-09-03 (analysis/deep-research/FLEET-SIGNAL-UNREADABLE-VERIFICATION-2026-09-03.md):** real race, zero quantified cost. Root cause: build_shared_signal.build() writes shared-signal.json with a non-atomic Path.write_text (truncate-then-write) and TWO 1-min writers race it (Gamma_FleetExecutor 09:31-16:01 and Gamma_SightBeacon 09:00-16:30, which also calls build()); fleet_live._load_signal reads once, no retry; all 106 exceptions Aug-1..Sep-3 are the empty-file fingerprint 'Expecting value: line 1 column 1'. CORRECTION: risky-1 was 6/38 unreadable-with-position, not 18/38 (filing error). Cost: of 12 such ticks, 10 had SPY points clear of the structure trigger; the 2 that mattered (09-02 765C) show no delay against readable neighbours and fills. DECISION (Fable): kill-type-adjacent DEFECT FIX for the 09-29 bundle -- writer tmp+os.replace, reader retry-once then fall back to the arm's last known closed 5m close, plus a concurrency guard test that reproduces the race pre-fix (build it on the bundle branch; prereg = zero unreadable rows over 5 forward sessions post-ship). :: status:verified-bundle-candidate

- [ ] RELEASE-BLACKOUT-FORWARD (HIGH, kill-type candidate, bundle 09-29 ONLY if the forward shadow clears; filed 2026-09-03 13:03 ET) :: `Gamma_ReleaseBlackoutShadow` 17:15 ET accrues per-release-day 1-minute adverse moves inside the window and what R1 (no entries T-15..T+5) / R3 (flatten T-2) would have done to real fills. History does NOT clear (R1 n=3 +$305 ex-best-day $0; R2 fails; R3 n=3 -$42; ISM-day worst-1-min option move -12.5% vs -8.6% non-release, CIs overlap). Prereg `analysis/recommendations/prereg-scheduled-release-blackout-2026-09-03.md` (frozen: >=3 forward ISM days with >=2 showing a >=15% adverse 1-min move AND ex-best-day net >= 0 on forward rows). Exhibits: 2026-08-05 and 2026-09-03 (four arms stopped by the 10:00 gap). Note R1's 09:45 start would NOT have caught today's 09:41 entry -- the forward read must include a T-20 variant as disclosure. :: status:shadow-running
- [ ] STRUCTURE-VETO-CLASSIFIER-FIX (HIGH, trading-path -> 2026-10-30 class; filed 2026-09-03 13:03 ET) :: `engine_cli._classify_sameday_5m` uses `crypto/lib/market_structure.classify_trend` (the module's own 'tentative fallback') with `find_swing_points(window=2)`, which cannot confirm the newest two 5m bars; today it read 'downtrend' 11:11-11:35 ET at SPY 770.7-772.9 during a 6-point rally and vetoed safe-2 (safe-3 inheritance via the shared safe signal: source says yes, ledger cannot confirm -- see VETO-SCOPE-SAFE-3-VERIFY). Fix spec (in `analysis/recommendations/structure-veto-lift-package-2026-09-05/README.md` section 5): swap to the authoritative `walk_structure` BOS/CHoCH machine with a confirmation-lag disclosure; guard = replay today's 11:16/11:21/11:27 bars and assert not 'downtrend'. The single-key LIFT (params.json:314 -> false) is NOT shipping Saturday: 08-23 replay battery DO NOT FLIP (n=15, p=0.836); gate-expiry YELLOW n=5 drop-top3 -$189; SPY-proxy WR 56.5% CI [35%,78%]. :: status:evidence-accruing -- EVIDENCE HALF SHIPPED 15:42 ET 2026-09-03: Gamma_StructureClassifierShadow 17:25 ET (registry 169), prereg-structure-classifier-swap-2026-09-03.md frozen. Backfill n=843 since 07-06: live veto correct at +30m 41.7% (CI 34-50%); walk_structure disagrees 39% of ticks and where it disagrees the live veto is wrong more often (diff -0.27, CI [-0.44,-0.10]); BUT walk would have vetoed all 5 entries on 08-06 and 5/25 on 08-13 -> the naive swap FAILS the frozen bar today; the 10-30 fix must be a confirmation-lag-aware variant or nothing. Code half stays open (engine_cli.py frozen).
- [ ] TRENDLINE-J-DRAWN-LINES-LEDGER (HIGH, instrument; filed 2026-09-03 18:30 ET) :: stop proxying J's eye with rules: nightly (after hours, TV up), read the trend lines J actually drew on the SPY chart via the TradingView MCP (`draw_list` / `draw_get_properties`, timeframe + anchor points + body/wick), persist them to `analysis/recommendations/j-drawn-lines-ledger.jsonl` (dedupe by anchors), and score each line's subsequent touches and breaks forward from cached 1m bars with the same event/outcome definitions as the human-anchor prereg; J's own anchors are the hypothesis, the forward tape is the test. Needs a prereg (frozen before the first read), the headless-draw plumbing already used by Gamma_TrendlineHeadlessDraw, and a Rule-9-safe schedule (16:30 ET). Build tomorrow evening with TV up; J asked 2026-09-03: it should be studied more, I see them every day with my eye. :: status:open
- [x] GITHUB-AUDIT-HISTORY-MODE-BROKEN (HIGH, security tooling; filed 2026-09-03 19:00 ET) :: `python setup/scripts/github_audit.py --history` crashes before scanning: the git-log subprocess is decoded with the cp1252 default (UnicodeDecodeError at byte 0x9d) and scan_history() then does diff_output.splitlines() on None (github_audit.py:341). So the ONLY tool that would have caught a secret already in history has never run to completion -- directly relevant to tonight's SECRETS-ON-PUBLIC-REMOTE. Fix: encoding='utf-8', errors='replace' + a loud non-None guard; test with a repo containing a non-cp1252 byte; then run the full history scan and report every finding. :: status:done -- FIXED + RUN 19:17 ET 2026-09-03: three subprocess call sites now decode utf-8/errors=replace and scan_history raises loudly instead of .splitlines() on None (a security scanner that no-ops is worse than one that errors); tests extended with a history fixture containing a non-UTF8 byte + fake key (13 passed). First completed run ever: 134 s, 14,028 files, verdict RED, 12 findings -> SIX distinct Alpaca credentials in PUBLIC history (see STATUS alarm), three of them key+SECRET pairs. This is exactly why the tool mattered: the hand-found leak was 2 of 6.
- [x] TRENDLINE-J-DRAWN-LINES-LEDGER (HIGH, instrument; SHIPPED 19:00 ET 2026-09-03) :: captured 23 of J's OWN trend lines live from the chart (2 engine [GTL] lines excluded of 25), read-only, resolution restored; ledger `analysis/recommendations/j-drawn-lines-ledger.jsonl` + scorer with no-look-ahead (status ACCRUING, 0 forward lines today by construction); prereg `prereg-trendline-j-drawn-lines-2026-09-03.md` frozen. KEY FINDING that reshaped it: TradingView's shape API is NOT timeframe-scoped (same 25 entity ids under 5m and 15m) and a shape's reported anchor time drifts up to ~62h with the active resolution -- so lines are deduped on the stable entity_id and timeframe is recorded as 'other' rather than fabricating a 5m/15m split. None of today's 23 matched J's narrated anchors exactly (closest: an ascending line 06:15->15:00) -- reported, not force-matched. Installer written, NOT registered (needs TV up at 16:30 ET; register tomorrow). 13 tests pass. :: status:done
- [ ] GITHUB-AUDIT-NO-LIVE-KEY-PATTERN (HIGH, security tooling; filed 2026-09-03 19:17 ET) :: `github_audit.py`'s SECRET_PATTERNS covers Alpaca PAPER key ids (`PK[A-Z0-9]{24}`) but has NO pattern for LIVE key ids (`AK...`) -- so a live-money credential could sit in the tree or history and every scan would read GREEN. Verified tonight that zero AK-shaped ids exist in history (so nothing is currently missed), but the blind spot is real and the stakes are the live account. Add the live-key pattern (and Alpaca secret-key shape, broker tokens, Discord/OpenRouter tokens if absent), with fixture tests per pattern; re-run --history after. :: status:open


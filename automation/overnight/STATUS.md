## [2026-09-02T16:15:03 ET] NOT_EXERCISED -- monday_verify (WEEKEND-TWELVE Next-Twelve #6): mechanical sweep for 2026-09-02 -- 5 GREEN / 0 YELLOW / 0 RED / 1 NOT_EXERCISED

**Mechanical checklist, not prose** (Next-Twelve #6: converts five pending-verifies into verified). Never blocks, never kills -- fail-open throughout; NOT_EXERCISED means the item's precondition never fired this run (C7: a check passing because nothing happened is not GREEN).

| Item | Verdict | Expected | Observed |
|---|---|---|---|
| WS7 live watch | GREEN | Gamma_LiveWatch fires ~1/min 09:25-16:10 ET (~405 ticks). On the first REAL open position, live-watch.json (and the log's in_trade count) should reflect it within ~2 minutes of fill, and per REQUIRED_POSITION_FIELDS every position field should populate non-null. | 401 RTH fires logged (09:25-16:10 ET, vs ~405 expected), 84 tick(s) showed in_trade>0. 33 real fill(s) dated 2026-09-02: bold-2@11:16, bold-2@11:17, safe-3@11:17, risky-1@11:17, bold-2@11:18, bold-2@11:19, bold-2@11:20, bold-2@11:56, bold-2@11:57, safe-3@11:57, risky-1@11:57, bold-2@11:58, bold-2@1… |
| WS6 regime stamp | GREEN | Gamma_RegimeStamp fires 08:22 ET weekdays (between Gamma_EmaSnapshot 08:20 and Gamma_Premarket 08:30): rebuilds regime-stamp.json and patches today-bias.json#regime_context, both dated the SAME session day, generated near 08:22 ET -- proving the first ORGANIC (truly scheduled) fire, not a manual re… | regime-stamp.json date=2026-09-02, generated_at_et=2026-09-02T08:40:01-04:00 (hhmm=08:40, in 08:15-08:40 window=True). today-bias.json date=2026-09-02, regime_context.stamp_date=2026-09-02 (present=True, dates_match=True). one_liner='Yesterday 2026-09-01 (Tue) = gap-go (range 0.68%, gap -0.64%, clo… |
| WS3 level hysteresis | GREEN | Friday 2026-07-31 PRE-FIX worst case: level 743.25 present 331/386 core ticks, 14 appear/disappear flips (fixed-replay showed 386/386, 0 flips). Hysteresis N=5 is live in production since 2026-08-01; every level's worst flip count today should sit well under 14, with hysteresis_held firing whenever… | 386 safe core ticks, 56 distinct near-price levels. Worst: 762.90 flipped 6x (vs Friday PRE-FIX worst 743.25 @ 14x, present 331/386). 171 level-refresh run(s) logged (171 ok), hysteresis_held fired 48 time(s) across 6 distinct level(s). |
| WS11 core recency | GREEN | Baseline frozen 2026-08-01 (25-trading-day rolling window ending 2026-07-31): bear RED n=10 exp=$-60.9/tr; bull UNDERPOWERED n=1 exp=$-295.0/tr. Watching whether n grows and/or either verdict moves as the rolling window advances past 2026-07-31. | run_date=2026-09-02 window_end=2026-09-01 (baseline window_end=2026-07-31, advanced=True). bear now: RED_CONCENTRATED n=31 (delta +21 vs baseline n=10) exp=$-1.77/tr, verdict_moved=True. bull now: GREEN_CONCENTRATED n=38 exp=$49.55/tr. live refresh attempted=True ok=True. |
| Theta cockpit | GREEN | Gamma_ThetaClock fires ~1/min 09:30-16:00 ET (~390 ticks). Historically theta_per_contract_per_day_source == 'sqrt_time_decay_model_est' on 29/29 real ENTER rows checked pre-build (the Alpaca options-snapshots greeks endpoint has returned {} every time) -- this run tests whether that streak is STIL… | snapshot ts_et=2026-09-02T16:00:00 (fresh_today=True) accounts_checked=['safe-3', 'safe-2', 'risky-1', 'bold-2']. 211 theta-clock row(s) dated 2026-09-02 across 4 position(s); sources seen=['sqrt_time_decay_model_est']. broker_snapshot=0, sqrt_time_decay_model_est=211, unavailable=0. still sqrt_tim… |
| WS1 preview diff | NOT_EXERCISED | MONDAY-PREVIEW-2026-08-03.md predicted, on a Friday-like tape: cores (safe-2/bold-2) 0 entries UNLESS block_elite_bull is flipped (still true/unapplied as of 2026-08-01); safe-3 ~1 fill; risky-1 ~2-4 fills (from 0 Friday -- 4 tradeable episodes / 32 in-window ENTER-plan ticks under the new bold_cor… | this preview is date-scoped to Monday 2026-08-03; checked date is 2026-09-02 -- diff not applicable. |

Full detail: `automation/state/monday-verify.json`. Re-run: `backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py --date 2026-09-02`. Guard: `backtest/tests/test_monday_verify_2026_08_01.py`.

---

**3. `## Known broken` had left the preamble again.** Yesterday's fix moved it to the top; a
producer prepended a dated entry at line 1 and it was back inside an entry, due to roll off
to the archive with it -- the 2026-08-20 two-month outage restarting on day one. Pinning by
POSITION cannot survive a producer that writes above you, so `status_retention` now pins by
NAME (`PINNED_SECTIONS`) and hoists the newest occurrence from anywhere. The positional guard
was replaced with the invariant it was a proxy for: does the section survive a real roll?

**Guards:** 14 new + 13 rewritten + 24; 10 mutations RED-proofed, each caught by the intended
test. Two of my own mutations initially ESCAPED (a fixture that buried the marker in an entry
that survives anyway; a "reads the live producer" test that asserted the regression's
spelling rather than its behaviour) -- both guards were strengthened, neither mutation
dropped. A third caught a real defect in my own hoist: every copy was being lifted, not just
the newest.

**Still open, split out:** `TRENDLINE-DRAW-HEADLESS` is the one REAL alarm of the three --
last run 2026-08-27, `reason="budget conservation"`, a string that appears in no code. An LLM
skipped a step whose work is a $0 deterministic script. Filed with the constraint-provenance
finding: `trendline_chart_draw.py` justifies its LLM-only design by citing a headless
constraint that `Gamma_ChartAutoDraw` had disproved **three days before that module was
written**. Fix path is proven, not speculative.

**Revoke:** `git revert 478dadf2`.

## Known broken

- [2026-09-02T16:40+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m. Roles are falling through to their next lane or the local floor. Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py. See automation/state/roster-health.json.
- [2026-09-02T15:07+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m. Roles are falling through to their next lane or the local floor. Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py. See automation/state/roster-health.json.
- [2026-09-02 10:15 ET] FULL-SUITE RED :: 11732 passed, 7 failed, 11 skipped :: tests/test_desk_allocator_kalshi_lane_fix_2026_08_21.py::test_live_kalshi_state_currently_healthy, tests/test_graduated_guards.py::test_free_model_cost_estimate_is_zero, tests/test_measured_move_study.py::test_preregistration_file_exists_and_is_frozen, tests/test_premarket_touch_credit_study.py::test_preregistration_file_exists_and_is_frozen, tests/test_quiet_mode_weekend_research_2026_08_30.py::TestPresenceDowngrade::test_gaming_outside_the_research_band_still_blacks_out, tests/test_structure_stop_study.py::test_preregistration_file_exists_and_is_frozen, tests/test_tw8_headroom_retest.py::test_preregistration_file_exists_and_is_frozen_v1 :: re-run: cd backtest && python -m pytest tests/ -q -m "not slow"
- [2026-09-02T14:14+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m. Roles are falling through to their next lane or the local floor. Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py. See automation/state/roster-health.json.
- [2026-09-02T07:48:41-04:00] MCP_AUDIT_YELLOW: Alpaca Safe (PA3POKNV46VG) + Bold (PA3WEBXJU67N) endpoints returning 404 (credential/account mismatch possible); TradingView CDP reachable; uvx processes active. Investigate key freshness before market open.
- [2026-09-02T11:00+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): openrouter::nvidia/nemotron-3-super-120b-a12b:free. Roles are falling through to their next lane or the local floor. Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py. See automation/state/roster-health.json.
- [2026-09-02T06:27:06] MCP_AUDIT_YELLOW: TradingView OK, Alpaca Safe/Bold MCP servers still connecting (session start)
- [2026-09-02T06:23:50.560122-04:00] MCP_AUDIT_YELLOW: Alpaca MCP servers not yet available; TradingView OK

> **This section is the PREAMBLE and must stay above the first `## [` entry.**
> `status_retention.py::split_entries` splits on `## [` headers and preserves only what
> precedes the first one. `## Known broken` does not start with `## [`, so anywhere below
> that line it is absorbed into the body of whatever dated entry precedes it and rolls off
> to the monthly archive when that entry ages out -- silently taking every producer that
> targets this marker with it (`guard_runner_slow.py`, `gate_expiry_check.py`,
> `twin_gauntlet_conductor_hook.py`, `prereg_hygiene.py`). That is the 2026-08-20 scar
> where three guards discarded RED for two months. It was fixed once and drifted back,
> because a session prepending a new entry pushes it down again. Restored to the top
> 2026-09-02 and pinned by `backtest/tests/test_status_known_broken_preamble_2026_09_02.py`.
> **Prepend new dated entries BELOW this block.**


- [2026-09-02T16:16 ET] conductor: OK -- QUOTE-TAPE instrument confirmed alive (closed queue item) + a live STATUS.md self-corruption found and fixed while writing this entry -- REVOKE surface

  **Picked via STAGE 0 budget gate PROCEED ($11.02/$30, 4/8 fires) + market closed (Wed 16:12 ET, RTH ended 16:00) + engine-health.json GREEN (22/22, market_open:false). `desk_allocator.py`: SPY 0DTE #1 (config-freeze-blocked). No un-actioned `GATE-BLOCKING` queue item. Fell through `task_scorer.py` ranking to `QUOTE-TAPE-HAS-NEVER-CAPTURED-A-SESSION` (HIGH, status:monitoring) -- its own filed action was "verify on the next trading day", and today is that day.**

  1. 🎯 **Quote-tape instrument verified alive and capturing -- CLOSED.** All 4 of the item's own Monday-gate checks now pass: (1) `Gamma_QuoteRecorderKeepalive` `State: Ready`. (2) `quote-recorder-status.json` `pid:9664`, `last_cycle_ts_et` fresh (16:11 today), `last_cycle_ok:true`. (3) `analysis/quote-tape/` now has two real session files (`2026-09-01.jsonl` 310 rows, `2026-09-02.jsonl` 592 rows and growing). (4) Re-ran `setup/scripts/trades_enriched.py` fresh: `exit_quote_matched: 15` / `exit_quote_match_rate: 0.0372` (up from 0/388/0.0), mean exit slippage **-$2.27/trade** vs resting bid on the 15 matched rows. Low overall rate is EXPECTED (recorder only matches forward from when it started running) -- no defect, nothing to fix in `quote_recorder.py`. Hygiene: added `analysis/quote-tape/` to `.gitignore` (own 90-day retention/pruning already in the recorder, `trades-enriched.jsonl`'s `exit_quote_*` fields are the tracked deliverable).
  2. 🔎 **While positioning this entry, found `## Known broken`'s own preamble was carrying a decoy.** Line 18 of the live file read `## Known broken\` had left the preamble again.** Yesterday's fix moved it to the top; a...` -- a fragment of an OLD bullet ("**3. `## Known broken` had left the preamble again.** ...", from the 07:20 ET STATUS-BROKEN-BLOCKS-DRAIN entry, still visible intact further down at what's now line ~549) that lost its `**3. \`` prefix somewhere upstream (root cause of the strip itself not fully reproduced -- flagged honestly, not claimed). `grep -c "^## Known broken"` returned **2**, not 1: the decoy and the true section (line 41) both matched at true line-start.
  3. ✅ **Root cause of the RISK, not just the symptom: `_extract_pinned`'s pin-match was `b.lstrip().startswith(name)` -- a prefix test that cannot distinguish "## Known broken" (the section) from "## Known broken\` had left..." (a decoy with the same prefix).** Fixed in `setup/scripts/status_retention.py`: new `_is_pinned_heading_line()` requires the block's FIRST LINE to equal the marker exactly (trailing whitespace only). Content repaired (prefix restored, ground-truthed against `git show 9841adfd`) so the live file now has exactly 1 clean marker line.

  **Verified, quoted (OP-33):** new guard `test_a_decoy_line_starting_with_the_marker_is_not_hoisted_as_the_section` in `test_status_known_broken_preamble_2026_09_02.py`, RED-proofed live (`git stash` the code fix with the new test's fixture unchanged -> 1 failed, quoted assertion: decoy content found inside the hoisted "pinned" block; restore -> 8/8 passed). No regression: all `status_retention`/`status_known_broken` tests = 37/37 passed. Curated safety gate: `python backtest/tests/run_safety_gate.py` -> **59 passed, PASS**. Frozen-file diff (`params.json`/`aggressive/params.json`/`heartbeat_core.py`/`filters.py`/`risk_gate.py`/`exit_manager.py`/`fleet_executor.py`/`strategies.py`/`build_shared_signal.py`/`accounts.json`) empty -- pure tooling + data-hygiene fire, config freeze untouched.

  **Rail (infra/tooling + observer-only content fix -- zero trading-path file touched, no order placed):** guard = the RED-proofed test (a); revert = `git revert` (2 commits: quote-tape verification/.gitignore, and the pin-match fix + STATUS.md content repair) (b); this entry is the REVOKE report (c).

  **Not done this fire, left open (stated so it isn't silently dropped):** the exact mechanism that stripped `**3. \`` from the original bullet was NOT reproduced -- only the downstream risk (the prefix-match pin-matching that let the decoy get treated as the section) was fixed and pinned. If this class of corruption recurs elsewhere in the file, the new guard will only catch it for the `## Known broken` marker specifically, not generically. Checked (not just flagged): `git show HEAD:automation/overnight/STATUS.md` already contained this same decoy (line 458, deep in an old entry) -- an EARLIER commit shipped it uncaught -- but `STATUS-archive-2026-09.md` was verified clean (`grep -c "Known broken"` = 2: one unrelated prose line, one legitimate single archived section header at line 800; no stray decoy duplicate there).

- [2026-09-02T06:27 ET] conductor: OK -- self-audit organ silent-truncation bug found + fixed (commit `b48c3732`) -- REVOKE surface

  **Picked via STAGE 0 budget gate PROCEED ($10.37/$30, 3/8 fires) + market closed (Wed 06:27 ET) + engine-health.json GREEN (22/22, market_open:false). `desk_allocator.py`: SPY 0DTE #1 (config-freeze-blocked). No ready `GATE-BLOCKING` item (both queue.md items already resolved/shipped this same night). Fell through to STAGE-1 priority #3: next untriaged self-audit batch = 2026-09-01T17:31:48 (12 gap-lines).**

  1. 🎯 **While reading that batch to triage it, found the batch itself was silently corrupted** -- its 12th gap-line reads "Systemic The live-watch field-completeness fix is sound, but the" (no trailing newline issue -- the newline IS there; the sentence itself is cut mid-clause, no `[...]` marker, indistinguishable from a real complete gap).
  2. 🔎 **Root cause (one sentence): the free perspective model hit its own output-token cap mid-generation, and the truncated fragment landed as the LAST line of its response, so `_extract_gaps`'s single-line bullet regex captured it intact while the 240-char `_soft_truncate` never fired (already short).** Verified against the raw consult JSON: `analysis/swarm-consult/2026-09-01-173002-...json` perspective 3 (`liquid/lfm-2.5-2.6b:free`) shows `output_tokens: 2500` == `max_tokens_per_perspective` exactly -- not a self_audit.py writer bug, not a process-reaper kill (checked and ruled out: the task launches via `wscript.exe .../pythonw.exe` and the swarm-consult child via the backtest-venv `python.exe`, both outside/exempt from `Stop-StaleClaudeProcesses`'s CIM filter+exemption list).
  3. ✅ **Fixed in `setup/scripts/self_audit.py`:** `_mark_if_incomplete()` appends the shared `[...]` marker when a bullet ends on a dangling function word (the narrow, specific signature of a token-cutoff mid-clause -- "...but the"), so a future truncated fragment is visibly flagged instead of silently read as a genuine gap. **First draft over-flagged** (required terminal punctuation, which real period-less headline gaps like "Filter 5/9 static thresholds" don't have) -- caught RED by the EXISTING `test_self_audit_extract.py` suite before shipping, narrowed to the dangling-word signal. Also bumped this caller's own `--max-tokens-per-perspective` 2500->4000 (self_audit.py only, no other `swarm_consult.py` consumer's default changes) to reduce recurrence.

  **Verified, quoted (OP-33):** new guard `test_self_audit_incomplete_marker_2026_09_02.py` (7 tests) RED-proofed live (`git stash` the fix -> 5/7 fail `AttributeError`; restore -> 90/90 passed across all self_audit test files: `test_self_audit_extract.py` + `test_self_audit_swarm_timeout.py` + `test_self_check_self_audit_organ_alive.py` + the new file). Curated safety gate: `python backtest/tests/run_safety_gate.py` -> **59 passed, PASS**. Frozen-file diff (`params.json`/`heartbeat_core.py`/`filters.py`/`risk_gate.py`/`exit_manager.py`/`fleet_executor.py`/`strategies.py`/`build_shared_signal.py`/`accounts.json`) empty -- pure tooling fire, config freeze untouched.

  **Rail (infra/tooling fire -- self-audit organ is observer-only, zero trading-path file touched, no order placed):** guard = the RED-proofed test file (a); revert = `git revert b48c3732` (2 files, fully additive, no existing function signature changed) (b); this entry is the REVOKE report (c).

  **Not done this fire, left open (stated so it isn't silently dropped):** the 2026-09-01T17:31:48 batch's 12 gap-lines themselves were NOT triaged -- the meta-bug in the producer was higher-leverage (fixes every future batch) than one batch's individual dispositions, and budget/scope favored shipping the fix over doing both. Next fire on the self-audit thread should triage that batch fresh (its own item 1, self-referentially, already warns about same-fire DONE-marker risk -- worth reading first).



**Picked via STAGE 0 budget gate PROCEED ($2.81/$30, 2/8 fires) + market closed (Wed 05:30 ET) + engine-health.json GREEN (22/22, market_open:false). `desk_allocator.py`: SPY 0DTE #1 (config-freeze-blocked). Checked `queue.md` for a `GATE-BLOCKING`-tagged item per STAGE 1 priority 2b (added 2026-09-01 specifically to stop this tier starving on the self-audit backlog) before falling through to `task_scorer.py --top` (which would have returned the suppressed `TWIN-DOCTRINE-FIRST-DEPLOY`) -- found `CRITERION-5-WINDOW-HAS-ZERO-SLACK`, filed 25 minutes earlier by the 05:15 Opus entry.**

1. 🎯 **The "genuine fork" in the 05:15 entry was already decided, just unread.** `automation/state/prod-shadow-designation.json` (written 2026-09-01T20:22 ET, BEFORE any prod-shadow result existed) states verbatim that the 2026-09-01..2026-09-29 / 20-day window is "the shorter, harder pass window" and the 10-30 clock is "EXTENDED disclosure view only." `go_live_gate.py`'s own report already renders it that way. Quoted into `queue.md` so it can't be re-litigated from a downstream summary again. Filed a reusable lesson: check for a `*-designation.json`/`PREREG-*.md` before treating an OP-0-exception-#4 fork as open.
2. ✅ **Shipped the now-gate-blocking catch-up sweep** (`setup/scripts/quiet_mode.py`, commit `6c8d7dc3`): a curated 9-name allowlist (McpDailyAudit, GitHubAudit, SpendSummary, OosCheck, LicenseMonitor, GateExpiryCheck, RosterLiveness, PreregHygiene, RuleBreakAudit) of $0-or-near-$0 report/audit/monitor tasks gets started, capped at 5/fire and most-overdue-first, when a daily trigger is proven (via `scheduled_task_staleness.py`'s own hold-attribution logic) to have fallen inside a presence hold. KalshiAuto/FuturesBrokerProbe/GuardsFull/GuardsNightly/ConductorWeekend explicitly excluded with reasons inline. Idempotent against a 5-minute enforcer cadence via a real-LastRunTime check not named in the original spec.

**Verified, quoted (OP-33):** 18 new guard tests (`test_quiet_hold_catchup_sweep_2026_09_02.py`) RED-proofed live (`git stash` -> 18/18 fail `AttributeError`; restore -> 18/18 pass). No regression: other 3 quiet_mode files + staleness suite = 102 passed; live starvation enumeration = 5 passed. Curated safety gate 59/59 PASS (both commits). `git diff --stat` against the 10 frozen trading-path files empty on both commits.

**Not done this fire (left open, stated so it isn't silently dropped):** no live end-to-end proof yet that the sweep catches a real missed fire (mocked-only this fire; first genuine overnight hold is the live proof -- worth a `quiet-mode.log` glance for a `CATCH-UP started` line next pass). J's `TASK-SCHEDULER-OPERATIONAL-LOG-DISABLED` one-liner unchanged (machine-wide OS setting, J-only).

**Rail:** paper/infra-only fire -- zero trading-path/params/heartbeat file touched (frozen-list diff empty on both commits), no order placed. Guard = the 18 RED-proofed tests (a); revert = `git revert 6c8d7dc3` then `git revert f1b09aa9` (both fully additive, no existing function signature changed) (b); this entry is the REVOKE report (c).

---

- [2026-09-02 04:52 ET] FULL-SUITE RED :: 11461 passed, 5 failed, 11 skipped :: tests/test_cheap_contract_qty_boost_2026_08_03.py::test_boost_fires_below_threshold, tests/test_cheap_contract_qty_boost_2026_08_03.py::test_threshold_is_strictly_below[0.49-10], tests/test_cheap_contract_qty_boost_2026_08_03.py::test_boost_never_shrinks_a_larger_plan, tests/test_graduated_guards.py::test_free_model_cost_estimate_is_zero, tests/test_queue_md_retention_cap.py::test_queue_md_under_retention_cap :: re-run: cd backtest && python -m pytest tests/ -q -m "not slow"
- [2026-09-02T08:50+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m. Roles are falling through to their next lane or the local floor. Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py. See automation/state/roster-health.json.
- [2026-09-02T07:23+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m. Roles are falling through to their next lane or the local floor. Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py. See automation/state/roster-health.json.
- [2026-09-02T06:36+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m. Roles are falling through to their next lane or the local floor. Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py. See automation/state/roster-health.json.
- [2026-09-02T05:37+00:00] ROSTER-LIVENESS: 1 lane(s) permanently DEAD (404/archived): p::m. Roles are falling through to their next lane or the local floor. Repoint in automation/state/model-roster.json, then re-run setup/scripts/roster_liveness.py. See automation/state/roster-health.json.

---

## [2026-09-02T14:20 ET] The 12th frozen prereg: a live behaviour resting on a run nobody can reproduce

Closed the last of the 12 frozen preregs that named a runner (work order section 2a) — and had
to correct my own diagnosis of it from this morning.

- **I said "bit-rot, the orchestrator signature changed". Wrong.** The signature never changed:
  the hook the runner calls **was never committed**. `git show --stat e84c062f` — the commit
  whose message says *"levels.py's new additive `memory_levels_by_day` hook"* — touches **six
  files, none of them engine code**, and `git log -S memory_levels_by_day` over
  `levels.py`/`orchestrator.py` returns **nothing across all history**.
- **So the recorded verdict cannot be regenerated.** `level-memory-wire.json` reports CONTROL 28
  / TREATMENT 26, n=3, −$489.50 — and no code here at any commit can produce that TREATMENT arm.
  Likely an uncommitted local edit (inference). The control does not reproduce either: **28
  trades in July, 36 today** on the same window.
- **A faithful rebuild would still measure the wrong thing.** The frozen treatment is side-blind
  *nearest-6*; the live wire changed **2026-07-27** to cap each side at 3, after J flagged that
  side-blind selection *"produced an all-resistance set with ZERO supports"*. The study encodes
  the version already known broken.
- **Retired as unrunnable — NOT a kill, NOT a pass.** The hypothesis is UNMEASURED. Reviving it
  needs a new prereg; re-pointing the frozen one would break its own `no_repick_clause`.
- 🚨 **What it leaves live:** `params.json` has `level_memory_live_merge: true` and
  `refresh_levels_intraday.py:700` really does merge memory levels into the live feed every
  intraday refresh — kept ON on *"insufficient n for a kill"* (n=3 vs a floor of 15) from the
  unreproducible scorecard. **Not turned off:** params.json is frozen to 10-30, and "we cannot
  reproduce the evidence" is not a verdict that the behaviour is harmful. Filed as
  `LEVEL-MEMORY-LIVE-MERGE-UNVALIDATED` with both options for the checkpoint.
- **Guard:** 5 tests, 2 mutations RED-proofed — pins the retirement, keeps the forensics on the
  prereg, and fails loudly *if the hook is ever built*, handing the builder a new prereg instead
  of a revival. It deliberately does not assert the flag should be false.
- Also filed `PREREG-BUILD-CLAIMS-ARE-UNFALSIFIABLE-AS-WRITTEN`: a generic "does the claimed
  build exist?" monitor **would have passed this** — file and function both exist, only the
  kwarg was missing. The fix is a structured `build_step` field, not a smarter regex. Not built
  today (n=2 across all preregs).

Section 2a's frozen-prereg box is now **[x]** — 12/12 runners resolved. Commit `be204a76`, no
engine file touched. REVOKE: `git revert be204a76`.

## [2026-09-02T11:35 ET] A rehearsal was being read as a real flatten -- by TWO safety checks

Went looking for the last stale baseline test and found a live false-green instead. The
`first_live_day_review` verdict came back **GREEN at 11:12 ET** -- for a day that had not
closed. That is the shape that is supposed to trigger suspicion, so I hunted the artifact.

- **What was in the ledger.** An early-close flatten REHEARSAL fired 06:14 ET with an
  injected clock and appended four rows to the PRODUCTION ledger
  `automation/state/logs/eod-flatten-2026-09-02.jsonl`, carrying `dry:true / outcome:NOOP`
  and stamped `12:45:00 ET` -- **hours ahead of their own write time**. The broker calendar
  confirms today closes **16:00**; there was no early close at all.
- **Two consumers read them as real**, both verified against the live file, not reasoned
  about: `first_live_day_review.py` reported *"Core flatten confirmed flat for bold-2
  (NOOP)"* four hours before the real 15:52 sweep, and `preopen_readiness.py` returned
  `eod_reality:Gamma_EodFlattenCore GREEN {safe-3, safe-2, risky-1, bold-2 all NOOP}` -- the
  pre-open readiness verdict -- **notify-only, it blocks nothing by design** -- certifying a
  drill as the safety net firing, i.e. the instrument that tells J the net is verified would
  have said so off a rehearsal.
- **Two defects, independently present in BOTH files:** `DRY_RUN` was a member of the
  accepted-outcomes set, and nothing filtered `dry:true`. In `preopen_readiness` the second
  is the dangerous half -- it keeps the LAST row per arm and rows are ordered by **append,
  not `ts`**, so a drill run AFTER a genuinely failed sweep DISPLACES the failure with a NOOP
  and the morning gate opens on a false green. The exact failure these checks exist to catch
  is the one a leftover drill row makes report clean.
- **Fixed both.** Rehearsals are excluded from evidence but COUNTED and NAMED in the reason
  (a ledger holding four rows that reports MISSING with no explanation is a report an
  operator argues with instead of acting on); only-rehearsals reports
  `MISSING_ONLY_REHEARSALS`/RED. Checked 08-21..09-01 first: **every** genuine production row
  carries `dry:False`, so the filter costs no real evidence and cannot go permanently red.
- **Also discharged the note left for "the next session that gets a green full run":**
  `GUARDS_FULL_EXPECTED_FAILED` **4 -> 0 ON EVIDENCE** -- the 11:09 ET run returned
  **11,739 passed / 0 failed / rc=0**, so the four tolerated failures were repaired, not
  re-baselined. **SCOPE, corrected 12:55 ET:** that run is `guard_runner_full.py`, which
  invokes pytest with `-m "not slow"`. It is the whole of what the nightly fire measures --
  so 0 is the right expected value for this check -- but it is NOT the whole suite. I called
  it "a green full run" in the commit message; that overstated it. One of the four baseline tests was a "clean day" fixture writing
  `status=red / failed=4 / returncode=1` -- incoherent, and harmless only because the check
  never read those two fields.
- **Guards:** 5 new tests (66 total) + 4 new (63 total); each defect RED-proofed
  **independently in each file** -- 4 mutations, all caught. Targeted sweep of the 10 modules
  touching `first_live_day_review`/`eod_flatten`: **187 passed, 1 skipped**. Full-suite
  re-run in flight.
- **Left open, deliberately:** `DRILLS-WRITE-INTO-PRODUCTION-LEDGERS` (queue.md). Hardening
  the readers closes this false-green, but nothing structurally stops a third reader making
  the same assumption. That is a refactor on an EOD-safety path and it is market hours.

Commit `a2683450` (7 files, no frozen trading-path file touched, safety gate 59 passed).
REVOKE: `git revert a2683450`.

## [2026-09-02T10:45 ET] All 7 guard failures fixed; clean run in flight -- REVOKE surface

The 10:15 ET full run came back **11,732 passed / 7 failed** (and the three cheap-contract
fixtures repaired this morning were GONE -- that fix held). All seven are now addressed, and
**not one was a real product defect**. Every one was a test or a schedule that ordinary
correct operation turns red.

- **4x prereg `is_frozen`** -- asserted `status == FROZEN_PENDING_RUN`; the preregs had been
  legitimately RUN and their verdicts recorded. A prereg's STATUS is a state machine correct
  operation advances; its CONTENT is what must never move. Replaced with a legal-state check
  that ALSO requires a `RUN_COMPLETE` claim to carry a `closed_*` run record -- something the
  old equality never checked. RED-proofed: an unfrozen DRAFT fails, RUN_COMPLETE with the
  record deleted fails, and editing a frozen population hash still fails the sibling
  anti-repick test. Commit `9e87eec8`.
- **quiet-mode gaming blackout** -- TIME-DEPENDENT. `presence_hold()` short-circuits inside
  the trading band (correctly -- the engine owns 09:30-15:55), so the test only ever passed
  outside market hours. Surfaced today because **this is the first full guard run ever
  executed during RTH** (the nightly fires ~04:29 ET). Now patches `_in_trading_band`.
- **Kalshi weather 49h stale** -- the test offered two explanations and **both were wrong**
  ("either the weather lane genuinely stopped, or the fix regressed"). The lane ran 08-31 with
  rc=0. Its 23:08 ET trigger clears the CLOCK blackout -- which is why the 2026-08-26 re-time
  looked sufficient -- but not the presence LINGER, which holds past 23:00 whenever the
  machine is in use. Caught the lane up (48.9h -> 0.0h, guard 6/6) THEN re-timed 21:08 ->
  23:40 MT; re-timing alone would not have gone green today. Registry updated.
- **`free_model_cost_estimate_is_zero` "flaky"** -- **not flaky, deterministic**. It failed in
  both full runs, passed alone (1 passed) and passed with its own whole file (129 passed,
  17.5 min). `test_eod_quant_guard.py` plants a fake `run_minimax` into `sys.modules` at
  IMPORT time and never removed it; alphabetically it collects BEFORE
  `test_graduated_guards`, which then imported the stub. Fixed with save/restore in a
  `finally` -- safe because `eod_fallback.py` binds `call_minimax` at module level and never
  re-consults `sys.modules`. RED-proofed on the reproducing order: leak restored -> 1 failed;
  fix in -> 9 passed.

**Clean run fired 10:45 ET** with all fixes in (the 10:31 run was killed -- it predated the
last fix, and a killed run writes nothing, so the 10:15 verdict was preserved; also backed up
to `guard-watch-full.json.good-1015`).

**The pattern worth naming:** 6 of 7 were guards that go red when the system behaves
CORRECTLY -- a prereg gets run, a study completes, the market opens, a task is caught up.
That is the "monitor that stays RED on known-correct behaviour" disease, and a suite carrying
seven of them is a suite nobody reads.

## [2026-09-02T09:33 ET] Criterion 5 FIXED -- window widened, evidence bar untouched -- REVOKE surface

Follows the 09:16 ET entry, which filed this as blocked-on-J. **J released it the same hour:**
*"THE HARD CODED 20 day logic was not my idea so it definitely can change depending on the
engines performance."* The original was written by an automated session executing
`PROD-SHADOW-ARM-DESIGNATION`, never ratified by J -- so it was mine to correct. Commit
`85e44e5f`.

**Changed:** `window_end` 2026-09-29 -> **2026-10-30**. **`min_days` UNCHANGED at 20.**

**Why that split matters.** Widening a window is a CALENDAR question; lowering `min_days` is a
STATISTICS question. Trading one off against the other silently is how a bar gets hollowed
out while still looking rigorous. The evidence content of criterion 5 is identical to what was
registered on 09-01; only the time allowed to accumulate it moved, and it was sized from
MEASURED PARTICIPATION -- knowable on 09-01, independent of any P&L. safe-3 filled 26 of 44
trading days (59%), so 20 scored days needs ~34 trading days; the old window gave 20, the new
gives 43 and clears the bar even at the worst arm's rate (bold-2, 47% -> exactly 20).
**safe-3's returns were deliberately not consulted in choosing the window.** 10-30 was already
the governing clock for the whole decision (work order S0), so this aligns criterion 5 with
the decision date rather than inventing one.

**The class fix is the real deliverable.** A bar that cannot be reached is a broken
instrument, not a strict one, and it fails in the most expensive direction -- it looks like
rigour, and the gate's honest-sounding `days_scored=0/20 INSUFFICIENT_DAYS` reads as "not yet"
rather than "never".
`backtest/tests/test_prod_shadow_designation_reachable_2026_09_02.py` now fails any
designation that: is unsatisfiable at a **47% participation floor** (the WORST arm, so a bar
cannot be tuned to whichever arm trades most); sets `min_days` equal to the window's trading
days (the literal 09-01 mistake); lets that floor drift above 50%; or lowers `min_days` under
cover of a calendar change. **RED-proofed: restoring the original 09-29 values fires it -- the
guard would have caught this on 2026-09-01.**

**Still true and unchanged:** the extended 40-day disclosure clock needs ~68 trading days at
59% and will not be met by 10-30. It is disclosure-only and gates nothing, but it will read as
unmet for the rest of the window -- worth a decision later, not a silent edit now.

**Revoke:** restore `prod-shadow-designation.json.pre-2026-09-02` over the live file (one
copy, no side effects); `git revert 85e44e5f` for the guard.

## [2026-09-02T09:16 ET] 🚨 J-DECISION: go-live criterion 5 is now UNREACHABLE ON BOTH CLOCKS -- arithmetic, not opinion

**This is the criterion the whole 2026-10-30 decision rests on, and it cannot be met as
frozen. It needs J, because fixing it means changing a bar that was registered before
results -- which I must not do (OP-11), and which gates live money (OP-0 #1).**

**The frozen bar** (`automation/state/prod-shadow-designation.json`, designated
2026-09-01T20:22, BEFORE any result -- legitimate, not gameable):
arm `safe-3`, window `2026-09-01..2026-09-29`, `min_days: 20`; extended clock `..2026-10-30`,
`extended_clock_min_days: 40`.

**A "scored day" requires a FILL.** `go_live_gate.py:729`:
`days_scored = len({r["date"] for r in window_rows})` over trade rows. An arm that correctly
sits out scores nothing.

**Primary window -- arithmetically impossible:**
- 2026-09-01..2026-09-29 contains **exactly 20 trading days** (Labor Day 09-07 excluded).
- The bar is **20**, so it requires a fill on **every single one**.
- 2 have elapsed (09-01, 09-02) with **0 scored** -- safe-3's last fill was 2026-08-28.
- Ceiling is now **18/20**. No performance can recover it.

**Extended clock -- not plausible either:**
- 41 trading days remain to 10-30; bar is 40 -> requires **98% participation**.
- safe-3's **measured** participation is **59%** (26 fills / 44 trading days, 06-29..08-28).
- Peers: safe-2 68%, risky-1 59%, bold-2 47%. None is near 98%.
- At 59%, expected scored days over 41 is ~24, not 40.

**The mechanism, in one sentence:** the bar was written as "20 scored days in a
20-trading-day window", which silently assumes **100% daily participation**, while the engine
sits out ~40% of days BY DESIGN -- "sitting out is a valid day" (J 2026-08-12). The bar and
the strategy are incompatible as written, and nothing checked that at designation time.

**What I did NOT do:** change the bar, widen the window, or redefine a scored day. All three
would be post-hoc bar changes on the live-money gate.

**J's fork (no doctrine default exists):**
1. Accept that criterion 5 cannot be met -> the 10-30 decision is made on criteria 1-4 with
   criterion 5 recorded as UNREACHABLE, or the decision moves.
2. Re-register the designation with a definition that counts a no-trade day as a scored day
   (defensible on "sitting out is a valid day", but it IS a bar change and must be J's, in
   writing, with the old one revoked explicitly).
3. Lower `min_days` to something reachable at 59% participation (e.g. ~24 of 41 on the
   extended clock) -- same caveat.

Revoke path for the designation is already documented in the file: delete it and
`prod_shadow_criterion()` falls back to NOT_WIRED with no other side effects.

## [2026-09-02T09:14 ET] Opus, Phase 0 top box: guards repaired, full re-run HUNG, review made honest -- REVOKE surface

**Correcting my own execution first.** §5.2 says "pick the top open box **in the current
phase**". Today is Phase 0 (§1, 09-01..09-05); every box I had worked came from §2, Phase 1
(09-08..09-26). I was executing the wrong phase and had skipped §5.2's read-the-matching-
judgment-chapter step. Re-running the cadence as written led straight to work I would not
otherwise have found.

**Phase 0's top box** (09-02 16:30 first-live-day review) cannot close until tonight, but its
own text names the precondition: the `guards_full` check "must not launder a fresh-looking
count off a stale state file". Working that under chapter 01:

- The box's premise is **stale**: `Gamma_GuardsFull` ran 02:29 local, `result=0`, state
  stamped `2026-09-02 04:52 ET`. Not dark.
- But its 5 failures were **all obsolete by 08:19**: 2 already passed, 3 were the known
  stale-fixture trio. Repaired (`fb34ca92`) -- asserting the **pre-clamp** qty from the cap
  note, because post-clamp qty is 5 in every case in that file and the obvious repair would
  have been vacuous. Ceiling NOT weakened. A 4th test was **passing and equally vacuous**;
  fixed, plus a non-vacuity guard.
- **The full re-run HUNG.** 43 min, 1078 CPU-seconds then flat, zero output,
  `guard-watch-full.json` never rewritten. Confirmed hung by sampling CPU twice (0.3s/20s),
  verified all 4 PIDs were mine (`guard_runner_full.py` + its pytest), killed. NOT relaunched
  into RTH -- re-running into the same conditions is the anti-pattern, and it would contend
  with the heartbeat for CPU. The scheduled task did the same work in ~23 min at 04:29, so
  the hang is manual-invocation-specific or intermittent. Filed.

**So tonight's review would have reported a false verdict**, and `Gamma_GuardsFull` next runs
**23:15 ET -- after the 16:30 review**, so it will not self-heal. The check measures staleness
in DAYS, and 04:52 is the same day, so 5 failures read as current. Day granularity cannot fix
this and shouldn't try: every same-day verdict is ~12h old by design, so flagging it would
make the check permanently yellow. Fix is information, not an alarm -- the reason now always
names the timestamp:
`YELLOW | failed count deviates from expected 4: got 5 [verdict recorded 2026-09-02 04:52 ET;
Gamma_GuardsFull next runs 23:15 ET, after this review]`

**Deliberately NOT changed:** `GUARDS_FULL_EXPECTED_FAILED = 4` is a tolerance that has
outlived its reason -- at 4 it reports GREEN for any four failures, including four new real
ones, and the four it was sized for are now repaired. It should be 0. I lowered it, saw four
tests encoding the old baseline go red, and **reverted**: 0 rests on the suite being clean and
the hang means I cannot verify that. A 0 on an unverified suite is a permanently-yellow check
-- the same disease inverted. Reasoning left in place; queue item
`GUARDS-EXPECTED-FAILED-BASELINE-IS-STALE` carries the exact follow-up.

**Market opens 09:30; stopping here.** Owed before 16:30: one green full guard run.

## [2026-09-02T08:06 ET] Opus: ARCHITECTURE refresh closed + a self-correction on tonight's own circuit study -- REVOKE surface

**Self-correction first.** `rolling_loss_circuit_study.py`, shipped 50 minutes earlier
tonight, hardcoded five arms and called them "the five arms trading real fills". That was
wrong when written: `accounts.json` says **risky-3 is `status: retired`, `live: false`** since
its 2026-08-28 retirement (last decision row 2026-08-28T15:54, last option fill 13:29). The
live roster is **four** -- safe-2, bold-2, safe-3, risky-1.

It matters beyond tidiness: risky-3 is 31 of the sample's trading days, and a retired arm
accrues no new ones -- so on the forward re-run "the circuit never tripped on risky-3" would
read as evidence when it only means the arm stopped trading. Fixed by READING the roster
(`active_arms()`), naming `retired_arms_in_sample` in the report, and printing a warning; the
prereg's forward plan now scores the four active arms only. Calibration deliberately KEEPS
risky-3's history -- those fills happened and the sample is thin. The fix was labelling, not
exclusion. Guards 16 -> 20, 3 more mutations RED-proofed. Commit in this block.

**`CLAUDE.md:66` carries the same stale claim** ("the 5 active real-fills arms ... risky-3"),
so the book-wide $500-1,000/day figure derived from it is overstated by one arm. **Filed into
the Sat 09-05 doctrine box, not edited** -- Rule 9 puts doctrine changes in the weekend pass,
in writing, with a documented reason. The doctrine text is where the stale claim originated,
which is why fixing it there is what stops the next copy.

**ARCHITECTURE.md refresh closed.** A parallel session had already landed the fleet layer,
exit_manager, order shape, halts and disclosed gaps in §3.2a (`3e114b62`) -- checked before
writing, did not redo. Added the three it did not reach:
- **§3.2b multi-symbol lane** -- a symbol-generic FORK, shadow-only (no order call exists in
  `multi/core.py`), and **paused in a way green tasks hide**: `Gamma_MultiCore` is `Disabled`
  with **300 missed runs** (last 2026-08-20, stopped on its own gate's null) while
  `MultiEvaluate`/`MultiOutcomes` still fire daily against a ledger frozen at 231 rows.
- **Tight-ladder caps** (3/5/$1,000) -- enforced by `risk_gate.cap_entry_qty`, verified called
  from BOTH money paths (`heartbeat_core.py:2740`, `fleet_executor.py:1331`).
- **The arming asymmetry** -- `live: true` means *places paper orders*, not live money; fleet
  arms are armed by the roster flag, the core pair by `GAMMA_CORE_ARMED=1` in
  `run-heartbeat-core.ps1:8` with **no `live` key at all**. The roster alone will never show
  you that core is armed.

**Session close:** 14 commits, all pathspec-scoped, zero frozen-path files touched. Guard
sweep 914 passed / 1 skipped. `engine_health` GREEN (`reds: []`).

## [2026-09-02T07:57 ET] Opus: full sweep 913/1 -- the 1 was MY regression from earlier tonight -- REVOKE surface

Commit `17453843`. Report-only monitor, no trading path.

**Found by running the sweep, not by the change's own guard.** Widening
`prereg_hygiene._results_index()` from `RECS_DIR.glob` to `ANALYSIS_DIR.rglob` earlier
tonight -- the change that took `n_has_results_file` 12 -> 105 and reframed the prereg
backlog from 52 aged items to 4 -- broke `test_registration_field_match_suppresses_the_flag`.
Its sandbox patches `RECS_DIR` but NOT `ANALYSIS_DIR` (computed from REPO at import), so the
index silently scanned the REAL repository instead of the sandbox: a result file sitting
directly beside its prereg was invisible and the prereg was flagged as never-run.

**I verified the widening against the NEW guard written for it and never re-ran this older
sibling.** The tell was there and I missed it: 7 sandboxed tests taking 18 seconds is the
signature of a function walking the real analysis tree.

Fix scans both roots, deduped by resolved path. In production RECS_DIR is inside
ANALYSIS_DIR so the second root adds nothing -- verified n_has_results_file still **105**,
n_flagged still 0, 127 files. It exists because the two are INDEPENDENTLY rebindable, and an
index must honour whichever directory it was actually pointed at. RED-proofed both
directions, each caught by the test that owns it.

**Sweep baseline for the next session:** 914 passed / 1 skipped across the 81 guard files
touching self_check, status retention, broker fills, task scorer, prereg hygiene, chart,
trendline and staleness.

**Revoke:** `git revert 17453843`.

## [2026-09-02] RECENCY-CONFIRMATION (confirm-before-capital gate) — RED-BLOCKED on the freshest 25 trading days (2026-07-27..2026-08-28), real OPRA fills, floor n>=10

> **Signal J wakes to (OP-25).** Weekly recency check (reusable `backtest/autoresearch/recency_check.py`, generalizes the Sunday fresh-revalidation; auto-reads OPRA cache last = 2026-08-28). The CONFIRM-BEFORE-CAPITAL gate: no live flip while an edge is RED; capital scaling waits for CONFIRM.
> - **Live-tier verdicts:** #1 ATM (Safe-2)=CONFIRM; #1 ATM (Bold)=CONFIRM; #2 ATM=YELLOW; #4 ATM=YELLOW
> - **Books:** Safe2_ATM_1+2+4=CONFIRM ($1274.05); Bold_ATM_1+2=CONFIRM ($269.4)
> - **edges_confirmed_on_recent = True** (any RED=True). CONFIRMED: #1 ATM (Safe-2), #1 ATM (Bold).
> - Files: `automation/state/recency-confirmation.json`, `backtest/autoresearch/recency_check.py`.

---

## [2026-09-02T08:30 ET] Opus, work-order §2d: CANARY-OUT-OF-SAFE-2 closed -- the item's own diagnosis was wrong -- REVOKE surface

Commits `6383274f` (fee residue) + `cc48a29f` (crypto bucket). Paper-only, additive, no
frozen file touched.

**16 phantom open lots vs a broker that says flat.** The queue item called it "FIFO float
dust (1e-4..1e-6 vs a 1e-9 threshold)". Measured rather than assumed: all sixteen were
**exactly 0.2500% of quantity bought**, across 6 arms and 6 symbols, from 4.2e-06 BTC to
**0.70 UNI (~$2)**. That is Alpaca's crypto taker fee charged IN THE BASE ASSET -- buy 100
UNI, pay 0.25 UNI, only 99.75 is ever sellable. Not dust: an epsilon big enough to swallow
0.70 UNI would swallow real positions. `dress_rehearsal.py` already carried the mechanism in
a comment ("fees can make position qty < order filled_qty"); nothing had connected it.

**Fixed as a classifier, not a matcher change.** My first cut popped fee-sized lots inside
the FIFO loop and silently destroyed **90 of 790 round-trip rows** -- a popped lot is no
longer available for a later fill to match against. The round trips and their P&L were never
wrong; only the leftover report was.
**VERIFIED COLD:** round trips 790 -> 790, realized P&L $1,283.45 -> $1,283.45 to the cent,
open lots **16 -> 0**, against a live `/v2/positions` read showing **0 positions on all five
live arms** (safe-1 401s -- dormant, same dead key as the structure-stop finding).

**Attribution: safe-2 reported n_manual=164.** 157 of those were the nightly $10 BTC canary,
because every crypto fill is hard-attributed "manual". That reads as J hand-trading 164
times. Crypto now has its own bucket, split on the SYMBOL (definitive; no state file, no
order-id registry, no heuristic). **n_manual 164 -> 7**, n_crypto 157, manual_pnl -47.08 ->
-46.00. Money was never the issue: crypto P&L is -$2.57 across the whole book.

**The canary STAYS in safe-2 -- decided, not skipped.** The item asked to move it to the twin.
Check 2 exists to prove safe-2's OWN auth+POST+fill+position machinery works tonight; moving
it proves some other account's machinery and silently drops that coverage. The defect was the
reporting. The go-live gate was never exposed either way -- it reads trades-enriched.jsonl,
which is options-only.

**Known limitation, pinned in a test:** a genuine position smaller than the fee residue is
indistinguishable from the fee by quantity alone and gets dropped. The broker's
`/v2/positions` is the only authority on flat (C11) -- which is exactly what exposed this.

29 guards, 9 mutations RED-proofed. Two escaped on my own weak fixtures and were fixed, not
dropped.

**Revoke:** `git revert cc48a29f 6383274f`.

## [2026-09-02T07:42 ET] Opus, work-order §2d: WEEKLY-CIRCUIT-BREAKER-CORE answered -- the answer is a NULL -- REVOKE surface

**No ship is proposed at 09-29.** Commits `3401e5fe` (study + prereg + guards), `c1e11540`
(test hygiene). Nothing armed; no frozen file touched.

**The gap is real.** Rule 5 is per-DAY, and the 08-18 day-throttle prereg already showed it
unreachable (worst arm-day -24.4% against a -30% floor). Nothing in the core path looks
ACROSS days. Real 3-day rolling realized losses: safe-2 -$640 · bold-2 -$955 · safe-3
-$1,306 · risky-1 -$1,214 · risky-3 -$1,252, on ~$5,000 accounts -- roughly -26% spread
across days that no per-day switch can see.

**The obvious fix is refuted.** 8-cell grid (W=3,5 x T=$400..$1000): **every cell cost the
book money** (-$53..-$1,718) and **6 of 8 made the worst per-arm drawdown DEEPER.** A circuit
breaker that worsens the drawdown it exists to limit is not a safety device.

**Mechanism, verified on a named case rather than asserted:** safe-3 lost -1048 / -156 / -102
over three sessions, tripping a 3-day/-$1000 circuit -- and the very next session was
**+457**. The circuit blocks the rebound. The window table agrees: safe-3's 10-day worst
(-482) is *shallower* than its 3-day worst (-1306). Drawdowns mean-revert in this record.

**What is frozen, and how weak it is.** W5/T800 and W5/T1000 are the only cells with positive
drawdown improvement, frozen for FORWARD judgement at 10-30. The caveat is stated up front
because it is load-bearing: at W5/T1000 the **entire +$133 comes from risky-1 blocking ONE
day (2026-08-12)**; W5/T800's gain clusters on 08-12..08-14. One mid-August event. The
correct prior is noise.

**Deliberately NOT logged as a kill.** The record contains no regime in which a drawdown
failed to recover, so it cannot speak to the case a circuit exists for. Absence of evidence
FOR these thresholds -- not evidence against multi-day risk control.

**Guards:** 16 tests, 8 mutations RED-proofed. Three initially escaped because MY fixtures
were too weak (a short-history case that never breached; a blocked day whose real P&L was a
win, which cannot distinguish carry-forward from zero). Fixtures strengthened, no mutation
dropped. The null is pinned so a flattering regression cannot become a silent green light.

**Also closed:** `TASK-SCORER-LIVE-QUEUE-TEST-FIXTURE` -- it had already gone RED exactly as
its filing predicted. The two ids it read from the live queue.md were completed and archived
by an ordinary consolidation (`b7f777b6`), so a parser guard failed for a reason unrelated to
the parser. Replaced with a snapshot of the incident's shape plus an id-agnostic liveness
check on the real file. Archiving a done item must not turn a guard red.

**Revoke:** `git revert 3401e5fe c1e11540`.

## [2026-09-02T07:20 ET] Opus, work-order §2d: STATUS-BROKEN-BLOCKS-DRAIN closed -- three causes, one symptom -- REVOKE surface

**Symptom:** `### BROKEN: self-check` blocks recurring every 30 min on a surface nobody reads.
Four blocks inside 23 minutes differed ONLY in a counter (13 -> 15 -> 17). Commit `478dadf2`.

**1. The re-append -- and the ping suppression was broken by the same line.** `_alert` wrote
STATUS.md unconditionally, and the Discord dedupe beside it keyed on `" | ".join(problems)`,
the FULL text. Half of self_check's messages embed a running count, so the key changed on
nearly every fire: STATUS.md grew a block per tick AND the 6h ping window never matched. One
shared `_problem_set_signature()` now gates both, collapsing free-standing numbers only (a
digit after a word char or hyphen stays -- `safe-2` must never collapse into `safe-3`).
*The downstream mitigation shipped 09-01 for this same spam (`fold_consecutive_selfcheck_
blocks`) folded 0 of the 5 live blocks -- they are not byte-identical. Same root cause
defeated both layers; this one is at the source.*
**VERIFIED COLD:** 4 consecutive runs 07:0x-07:16 ET, blocks held at 5, zero new Discord
pings since 06:59 -- while the underlying count really did move 19 -> 22.

**2. CHART-DRAWING was a FALSE ALARM against a retired producer (C14).** It watched
`key-levels.json -> chart_drawing_summary.as_of`, written by premarket Step 5 (an LLM step).
`Gamma_ChartAutoDraw` replaced that 2026-08-06 ($0, 08:35-16:05 ET /30m) and stamps
`chart-autodraw.json`, so the old field froze at 2026-06-29 while the chart was in fact
being redrawn correctly every day (verified: as_of=2026-09-01T16:05 ET, status=OK,
dry_run=false, real removals at spot 761.57, task GREEN). Re-pointed, and gated on `status`
too -- `draw_key_levels.py` write_state()s on its failure paths, so a bare date check reads
GREEN on a TradingView-down morning with a stale chart.

**3. `## Live watch

- [2026-09-02T14:28:01 ET] THETA STALL :: safe-2 SPY260902C00766000 qty=3 :: est theta burn -5.40 vs est delta gain +0.00 over last 15min (mid=0.415, unrealized=-32.76%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-09-02T12:14:01 ET] THETA STALL :: risky-1 SPY260902C00765000 qty=5 :: est theta burn -13.55 vs est delta gain -47.50 over last 15min (mid=1.395, unrealized=25.22%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-09-02T12:14:01 ET] THETA STALL :: safe-3 SPY260902C00765000 qty=3 :: est theta burn -8.13 vs est delta gain -28.50 over last 15min (mid=1.375, unrealized=24.32%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-09-02T11:37:00 ET] THETA STALL :: safe-3 SPY260902C00766000 qty=3 :: est theta burn -7.08 vs est delta gain +0.00 over last 15min (mid=1.05, unrealized=11.83%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
- [2026-09-02T11:25:00 ET] THETA STALL :: risky-1 SPY260902C00766000 qty=5 :: est theta burn -5.80 vs est delta gain +0.00 over last 15min (mid=0.955, unrealized=4.3%) -- ALERT ONLY, never auto-exits. detail: automation/state/theta-clock.json
_Standing visibility-only flag surface (THETA COCKPIT, 2026-08-01 J directive) -- NOT a breakage list, no auto-exit ever. Producers append ONE loud line here on a NEW stalled-position threshold crossing; never re-fired for the same position. Producer: setup/scripts/theta_clock.py._

---


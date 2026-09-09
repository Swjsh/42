# GOAL: WAVE-DAY-CONDITIONS-2026-09-05

> Opened by Fable 2026-09-05 12:01 ET. J's standing question: "why did we have big winner days last month
> and are we set up to have them again." The rig side is answered (doctrine: August 2026 big-day
> anatomy; five 2x BULLISH_RECLAIM wave days; rig verified intact). The market side is not: what
> did those mornings look like BEFORE 09:41 ET, versus the zero-wave days? This is a hypothesis
> GENERATOR with n=5 wave days -- it must never become a filter or a gate from this evidence.
> Its product is a prereg for the forward window and a $0 pre-market instrument row so the
> conditions are recorded every day from Tuesday on, and the ledger (not August) decides.

## DONE-WHEN
(W1) For every session 2026-08-03..today with a right-tail ledger row (analysis/right-tail/
ledger.jsonl + the 1-min variant): label the day wave / no-wave (>= 1 genuine wave per
backtest/lib/right_tail_waves.py). For each day compute, from cached SPY/VIX bars and the
existing premarket artefacts only (today-bias.json, key-levels.json, futures/ES overnight if
cached; $0; no new vendor): overnight gap % (open vs prior close), first-15-min range / 20-day
ATR, opening VIX vs prior close and VIX 5-day slope (C5: VIX character, not level), prior-day
close relative to prior-day VWAP, day of week, distance of the 09:30 print to the nearest
key-levels.json zone, and whether premarket bias called the direction. Table in
`analysis/right-tail/WAVE-DAY-CONDITIONS-2026-09-05.md` with the n disclosed on every row.
(W2) Honest read: which conditions separate the wave days at all (report effect direction and
overlap, never a p-value at n=5); explicitly list the conditions that DON'T separate. No
threshold is proposed. One prereg `analysis/recommendations/prereg-wave-day-conditions-10-30-
2026-09-05.json` (schema: prereg-not-flat-second-wave-10-30-2026-09-05.json): H = the top 1-2
separating conditions raise wave-day odds in the forward window; instrument = the daily row
from W3; evaluation at n >= 20 forward sessions; kill rule = no separation at n=20; class =
INFORMATIONAL (no trading-path use before a separate 10-30 prereg passes). Hygiene 0 flagged.
(W3) `setup/scripts/wave_day_conditions.py`: computes the same row for TODAY at premarket
(reads the same inputs, $0), appends to `analysis/right-tail/wave-day-conditions.jsonl`, and
is registered as a Windows task `Gamma_WaveDayConditions` at 09:20 ET weekdays via the
existing hidden-chain pattern (copy Gamma_RightTailCapture's registration; LogonType matches
the other Gamma_* tasks; documented in SCHEDULED-TASKS.md; the scheduled-tasks doc test green).
At 16:20 ET the right-tail capture already labels the day, so the join is by date. The cockpit
payload gains the row (backend only; the /cockpit UI reads what the payload has) -- computed-
but-unrendered is the recurring failure, so quote the payload key present in payload.json.
(W4) Guard tests: the script runs on a day with missing inputs and writes a row with nulls
(never crashes, C7); the ledger join labels a known August wave day as wave=true.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: no trading-path edits (FROZEN_TRADING_PATH in the pre-commit hook); measurement, instruments, off-path fixes, preregs only.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly. No task chips.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire; workers never edit STATUS.md or commit -- the orchestrator does.
- Every stamp is read from `python setup/scripts/et_clock.py` in the same call, never typed.
- Every fix ships with a RED-proofed test (the test fails on the pre-fix code) and one-sentence root cause.
- Verify, don't claim: every DONE item quotes the command output that proves it.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] W1 (DONE: 2026-09-05 14:58:51 ET, Fable session a16e320c worker W) -- per-day conditions table for 08-03..today, wave/no-wave labelled from the right-tail ledger; n on every row. -> analysis/right-tail/WAVE-DAY-CONDITIONS-2026-09-05.md (25 dates, 20 wave/5 no-wave).
- [x] W2 (DONE: 2026-09-05 15:00:14 ET, Fable session a16e320c worker W) -- honest read (separates / does not separate) + INFORMATIONAL prereg for 10-30; hygiene 0 flagged. -> analysis/recommendations/prereg-wave-day-conditions-10-30-2026-09-05.json; prereg_hygiene: 143 files, 0 malformed, 0 flagged.
- [x] W3 (DONE: 2026-09-05 15:03:09 ET, Fable session a16e320c worker W) -- wave_day_conditions.py daily premarket row + Gamma_WaveDayConditions 09:20 ET task (registered State=Disabled, verified) + cockpit payload key `righttail.wave_day_conditions_latest` quoted present in gamma-companion/public/payload.json.
- [x] W4 (DONE: 2026-09-05 15:06:09 ET, Fable session a16e320c worker W) -- guard tests (nulls on missing inputs; August anchor labels wave=true). -> backtest/tests/test_wave_day_conditions_2026_09_05.py, 4/4 passed, RED-proofed (bug-injected run failed as expected, reverted, re-passed).
- [x] W5 (DONE: 2026-09-06 16:09 ET, conductor-weekend fire) -- `big_day` (>=2.0x priced peak_multiple, same CAPTURE-<date>.json waves, no new pricing) added to `wave_label()`, the W1 backfill table, the prereg (new second-outcome section), and picked up by the cockpit key for free (it serializes the whole row). Actual split is n=14 big_day / n=11 not (NOT the goal item's assumed "n=5 vs 20" -- that assumption conflated the doctrine's top-5 DOLLAR-outlier days with "any wave reached 2x"; disclosed as a real, material mismatch: 4/5 dollar days overlap but 2026-08-06 does not, since its one wave peaked at 1.85x). W2.5 honest read: no condition separates big_day vs not; the primary wave/no-wave leans (Monday, overnight-gap%) do not reproduce (Monday lean vanishes, gap% lean reverses direction). No threshold/gate proposed. Commit `c3d5a387`.

## J-DECISIONS
- None. This never touches a gate before its own 10-30 prereg.

## PROGRESS LOG
- 2026-09-05 15:08 ET -- Fable: W1-W4 verified (9 tests, hygiene 0 flagged, task enabled Mon-Fri 07:20 MT on the silent pattern, first fire Tue 09-08); W5 queued for the conductor (2x-day label).
- {now} ET -- authored by Fable (Saturday morning session).
- 2026-09-05 14:46:21 ET -- Sonnet worker W started. Read right_tail_waves.py, right_tail_capture.py, edge-master-doctrine.md "August 2026 big-day anatomy", ledger.jsonl/ledger-1min.jsonl (244+252 rows, 25 dates 08-03..09-04).
- 2026-09-05 14:58:51 ET -- W1 done: built `setup/scripts/wave_day_conditions.py` (build_row/wave_label/etc), ran it over all 25 dates, wrote `analysis/right-tail/WAVE-DAY-CONDITIONS-2026-09-05.md`. Wave label = CAPTURE-<date>.json n_waves_meeting_threshold>=1: 20 wave / 5 no-wave (not the doctrine's narrower n=5 dollar-outlier set -- reconciled in the doc's method notes).
- 2026-09-05 15:00:14 ET -- W2 done: honest read written into the same md (day-of-week Monday lean + overnight-gap-% lean carried as top-2; 6 other conditions disclosed non-separating, ranges/n on every line, no threshold proposed). Prereg filed: `analysis/recommendations/prereg-wave-day-conditions-10-30-2026-09-05.json` (class INFORMATIONAL). `prereg_hygiene.py` -> `143 files, 0 malformed, 0 flagged`.
- 2026-09-05 15:03:09 ET -- W3 done: `install-wave-day-conditions.ps1` written (cloned install-right-tail-capture.ps1's wiring) and run via the PowerShell tool. `Get-ScheduledTask -TaskName Gamma_WaveDayConditions` -> `State=Disabled` (verified live, two separate checks). SCHEDULED-TASKS.md row added under "Wired -- NOT yet enabled" (NOT the Active table, so the "181 registered" Active-count header was left untouched -- confirmed via `test_active_stated_count_matches_table`). Cockpit key added: `gamma_cockpit_righttail.py` `_wave_day_conditions_latest()`, additive field on all 3 return paths. Ran `wave_day_conditions.py --date 2026-09-05` (real append) then `gamma_home.py --quiet` (no dev server started) and confirmed `gamma-companion/public/payload.json`'s `righttail.wave_day_conditions_latest` key is present with today's (all-null, Saturday, pre-open) row.
- 2026-09-05 15:06:09 ET -- W4 done: `backtest/tests/test_wave_day_conditions_2026_09_05.py`, 4 tests, `4 passed in 0.86s`. RED-proofed: injected a bug in `wave_label()` (ignored `meets_threshold`), reran -> `1 failed` (test_known_no_wave_day_joins_to_wave_false, `assert True is False`) exactly as expected, reverted the injected bug, reran -> `4 passed`. Full related suite (`test_wave_day_conditions_2026_09_05.py` + `test_scheduled_tasks_doc.py` + `test_right_tail_waves.py` + `test_right_tail_capture_gap_fixes.py` + `test_right_tail_1min_fail_open_2026_09_05.py`) -> `28 passed in 18.16s`.
- 2026-09-06 11:19 ET — opened by goal_autopilot
- 2026-09-06 16:09 ET -- conductor-weekend fire: W5 DONE. Picked via STAGE 0 budget PROCEED ($0.44/$30, 0/8 fires before this) + market closed (Sun) + engine-health.json RED only on the already-actioned `rth_tick_gaps` 09-04 gap (unchanged) + active-goal pointer resolved directly to this goal's only open item (W5), outranking desk_allocator/task_scorer/self-audit tiers per the priority order. Implemented `BIG_DAY_THRESHOLD=2.0` in `wave_day_conditions.wave_label()` (reuses CAPTURE-<date>.json's already-stored per-wave `peak_multiple`, no new pricing); backfilled all 25 sessions -- big_day=true 14/25, explicitly NOT the doctrine top-5-dollar-day set (4/5 overlap, 08-06 misses at 1.85x peak); added the W1 table column, W2.5 honest read (no separator found, primary-read leans do not reproduce), the prereg's `second_outcome_big_day_2026_09_06` block (kill rule unchanged, no hypothesis leg added), and the cockpit pickup verified free (same row, no separate edit needed). Verified, quoted (OP-33): 3 new guard tests (anchor-day true, 1.3x-only-day false, missing-capture null) -> `pytest tests/test_wave_day_conditions_2026_09_05.py -q` -> **7 passed** (was 4). RED-proofed via scoped `git stash push -- setup/scripts/wave_day_conditions.py` -> **3 of 7 failed** with `KeyError: 'big_day'` (the exact missing-gap signature) -> stash pop -> **7/7 green** again, `git diff --stat` confirmed clean restore. Broader `pytest tests/ -k "wave_day_conditions or right_tail_waves or right_tail_capture" -q` -> **23 passed**. Curated safety gate `tests/run_safety_gate.py` -> **59 passed, PASS**. `py_compile` OK. `git status --porcelain` scoped to the 4 intended paths before staging confirmed no absorption from this shared checkout's other dirty files. Committed `c3d5a387` (4 files, +157/-28). `prereg_hygiene.py` -> 143 files, 0 malformed, 0 flagged (22 result_exists_status_stale, pre-existing, unrelated).
- 2026-09-06 16:10 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
## HONEST STATE
W1-W5 all DONE, all verified this session. UNVERIFIED / left for Fable: (a) the day-of-week and overnight-gap-% leans are directional-only at n=5 no-wave days, per the goal's own no-p-value instruction -- they are hypotheses in the prereg, not findings; (b) the Gamma_WaveDayConditions task has never actually fired live (registered Disabled, per the operating rules workers never enable a task) -- its first real premarket row is unverified until Fable enables it and it fires on a real weekday morning; (c) 8/25 journal files have no "Bias:" line at all (08-12/13/14/17/31, 09-01/02/03/04) and 2026-08-31 has no per-day 1-min SIP cache (first-15-min/ATR20 falls back to the 5-min aggregate, which lacks 1-min granularity) -- both are real, disclosed data gaps, not bugs; (d) NEW -- big_day (W5) is a disclosure-only label with no active hypothesis leg (the honest read found no separator); if a later re-read of the accruing forward wave-day-conditions.jsonl finds one worth testing, that needs its own prereg addendum, not silent inclusion in the existing kill rule. QUEUE is now fully DONE -- next fire should check whether Fable/goal_autopilot has closed this goal before looking here again.
AUTOPILOT CLOSE 2026-09-06 16:10 ET: queue fully terminal (no bare '- [ ] ' item left)

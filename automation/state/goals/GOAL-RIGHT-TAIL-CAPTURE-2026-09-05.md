# GOAL: RIGHT-TAIL-CAPTURE-2026-09-05

> Opened by Fable from J's 2026-09-05 ask ("figure out why we had high-winner days last month and
> ensure we are set up to have big wins again"). The answer is on record
> (markdown/doctrine/edge-master-doctrine.md "August 2026 big-day anatomy"): the month was five
> two-trigger BULLISH_RECLAIM wave days taken 09:41-10:22 ET and held to the 2x TP1, plus a noon
> second wave. This goal turns that answer into a standing instrument so "are we still catching
> the waves" is answered every day by a script, not by a session.

## DONE-WHEN
A $0 daily instrument `setup/scripts/right_tail_capture.py` (registered `Gamma_RightTailCapture`,
16:20 ET weekdays, after Gamma_ZeroEnterAutopsy 16:10) writes `analysis/right-tail/CAPTURE-<date>.json`
+ a rolling `analysis/right-tail/ledger.jsonl` scoring, per session and per arm: (a) did a >=1.3x
wave exist on the tape (an ENTER-eligible tick whose contract later printed >=1.3x its ask within
the session, from core-decisions.jsonl + the OPRA cache the zero-enter autopsy already reads);
(b) did the arm take it (fills-ledger), at which tick relative to the first eligible tick; (c) did it
hold to TP1 (2x) and did the runner run; (d) was a SECOND wave (>=60 min after the first exit)
present / taken / refused, and if refused by WHICH gate (max_same_day_roundtrips=4, -$400 stop,
NOT_FLAT, settlement, structure veto, filter 8/10) -- this is the forward ledger the TIGHT-LADDER
prereg's 09-29 checkpoint question needs; (e) a 20-session rolling capture rate per arm on the
cockpit (rendered, not just computed -- the recurring failure). Backfilled 2026-08-01 -> today,
with the five August big days reproducing the numbers already in edge-master-doctrine.md.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: read-only instruments, preregs and shadow work only.
  Nothing in `setup/hooks/doctrine.py` FROZEN_TRADING_PATH is edited; any knob change the evidence
  indicts is filed as a prereg for the 09-29 (kill-type reduction) / 10-30 checkpoint, never shipped.
- Every fire that touches this goal calls
  `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly. Fable/Opus = spec + adjudication only.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation are the only
  sanctioned continuation paths.
- Reuse before rebuilding: name the existing script/ledger each item composes; never a parallel
  instrument for a question an existing organ already answers.
- Every number reported is quoted from a command run in the same fire (OP-33); UNVERIFIED stays labeled.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] R1 (DONE 2026-09-05 02:20 ET, `pytest backtest/tests/test_right_tail_waves.py` 4/4 green, RED-proofed by 10x'ing entry premium -> 1 failed / reverted -> 4 passed; core-decisions.jsonl has no rows before 2026-08-26 so 08-04 runs in a documented FLEET_FALLBACK mode instead of the goal's assumed core-score path) -- Define the wave: write `backtest/lib/right_tail_waves.py::find_waves(date)` composing
  `zero_enter_autopsy.py`'s per-bar table + the OPRA cache pricing path: a wave = first ENTER-eligible
  tick (score >= 9 either side, no blocker) whose ATM contract ask later prints >= 1.3x within the
  session; returns start tick, peak multiple, peak time, side. Validate by hand against 2026-08-04
  (waves at ~09:56 and ~12:28, both >= 1.9x) and 2026-09-02 (13 bull fills, all lost: expect waves
  present but peak < 1.3x, or none). DONE-WHEN: `pytest backtest/tests/test_right_tail_waves.py`
  green with those two fixtures, RED-proofed.
- [x] R2 (DONE 2026-09-05 02:25 ET; CORRECTED 2026-09-05 later fire -- reader-truncation fix: the "+$758 vs +$662" framing below was itself a false conflict. The +$758 is the two paying waves' GROSS from journal/trades.csv (270+113+254+121); +$662 is safe-2's full DAY NET, which additionally nets a real 13:41 ET -$96 loss. Both numbers are correct -- they answer different questions, neither supersedes the other. Original text preserved below for the record.) `setup/scripts/right_tail_capture.py` reproduces risky-1's 08-04 12:28 wave exactly: taken, exit_multiple 2.4737x, `would_be_refused_under_cap4: true` (its 5th same-day entry); safe-2 08-04 net was recomputed as +$662 not the goal's stated +$758 -- evidence correction, flagged not forced, see SUMMARY.md) -- Capture scoring per arm: join waves to `automation/state/fills-ledger.jsonl` (and
  `journal/trades.csv` for exit multiples): taken / missed / refused-by-gate, latency in ticks,
  held-to-TP1 bool, runner multiple. Refusal attribution reuses the gate ids already in
  core-decisions rows (`bear_blockers`/`bull_blockers`) and the fleet decisions' reason strings
  ("same-day entries", "1 triggers < 2", "requires confluence/sequence", "position already open").
  DONE-WHEN: 2026-08-04 reproduces safe-2 +$758 / risky-1 wave-2 refused-by-nothing (it was
  entry #5 -- flag it as `would_be_refused_under_cap4: true`).
- [x] R3 (DONE 2026-09-05 02:30 ET, Gamma_RightTailCapture registered 16:20 ET weekdays, State=Ready verified via Get-ScheduledTask; `pytest tests/test_scheduled_tasks_doc.py tests/test_install_script_times_match_registry_2026_09_03.py tests/test_right_tail_waves.py` 10/10 green) -- Instrument + task: `setup/scripts/right_tail_capture.py --date`, installer
  `install-right-tail-capture.ps1` (hidden pythonw chain, venv, -Daily, 16:20 ET = 14:20 local),
  SCHEDULED-TASKS.md row, `test_scheduled_tasks_doc.py` + install-times guard green, State=Ready.
- [x] R4 (DONE 2026-09-05 ET, this fire -- root cause found and fixed: `pytest backtest/tests/test_right_tail_waves.py` 10/10 green, RED-proofed (old fixture asserting 10:00/13:00/13:35/15:40 fails against the fixed code). Root cause (one sentence): the old CORE_SCORE eligibility test (bull/bear score>=9, zero blockers, deduped last-occurrence-per-5min-bar) anchored on a persistent "still admissible" field instead of the engine's own one-shot `verdict` (ENTER_BULL/ENTER_BEAR) field, and read only the `safe` core account -- fixed by anchoring directly on `verdict` in {ENTER_BULL,ENTER_BEAR} + setup in the doctrine ribbon shape, unioned across both core accounts (safe+bold), no bar-dedup. All 8 doctrine anchors across the 5 big days now reproduce within 2 ticks and clear 1.3x (08-04 09:56 exact/12:26 2-tick-early; 08-06 10:31 exact; 08-13 09:51 exact/14:36 exact; 08-27 09:41 exact/11:51 1-tick-early; 08-28 10:21 exact) -- full table in analysis/right-tail/SUMMARY.md. Three peaks (08-04 09:56, 08-27 09:41, 08-28 10:21) legitimately exceed the doctrine-quoted REALIZED runner exit multiple because SPY kept drifting for hours after every arm's own exit (verified via core-decisions.jsonl `spy` field) -- a real existence-vs-capture gap flagged for R2, not a detector bug, and not closed by fixture-tuning the pricing window. Re-backfilled 2026-08-01->09-04 (25/25 days, 0 errors): whole-backfill capture safe-2 80.6%/bold-2 61.1%/safe-3 58.3%/risky-1 72.2% (36 waves/arm, union of both core accounts); cap-4 would-refuse flags 11. 20-session cockpit tile: 67% book capture / 8 cap-4 flags (verdict amber), verified via `gamma_cockpit_righttail.build()` and payload.json regeneration.) -- Backfill 2026-08-01 -> today; write `analysis/right-tail/SUMMARY.md`.
  rate, median latency, share of waves refused by each gate, second-wave refusal count). The five
  August big days must reproduce edge-master-doctrine.md's numbers; any mismatch is a bug in R1/R2,
  not a new finding.
  **CORRECTED (2026-09-05, reader-truncation fix)**: this DONE claim rested on core-decisions.jsonl
  running in FLEET_FALLBACK mode for 08-01->08-25, which was itself a bug (see `right_tail_waves.py`
  module docstring + `conductor_outcome._row_day`): `_decisions_for_day` filtered strictly on a
  `date` key that `heartbeat_core.py` only started writing 2026-08-25; every earlier row (776 real
  rows for 08-04 alone) was silently excluded. Fixed (falls back to `ts_et[:10]`); 08-01->08-25
  re-backfilled in the correct CORE_SCORE mode (see SUMMARY.md's "The five August big days --
  re-verified" section for the new per-day numbers). Per the QUEUE item's own instruction ("any
  mismatch is a bug in R1/R2, not a new finding") -- **this mismatch WAS the bug**: 08-04 keeps the
  qualitative shape (different times/peaks); 08-06 now shows 0 core-safe-account waves and 08-13
  shows 1 instead of 3 -- a genuine, separate finding about `_dedup_by_bar`'s single-account
  last-occurrence-per-bar semantics (documented, not re-tuned this fire -- out of this fix's scope).
  Whole-backfill capture: safe-2 71.4%, bold-2 51.4%, safe-3 60.0%, risky-1 54.3% (was 79.4/61.8/
  73.5/85.3% under the wrong mode -- risky-1's drop is largest because the old fallback waves were
  partly self-referentially anchored to risky-1's own admission ticks). 20-session cockpit tile:
  65.4% book capture / 6 cap-4 flags (was 77%/8, `gamma_cockpit_righttail.build()` quoted both ways
  this fire). Tests updated + a new RED-proof test added
  (`backtest/tests/test_right_tail_waves.py::test_2026_08_04_core_decisions_has_date_is_true_never_fallback`).
- [x] R5 (DONE 2026-09-05 02:28 ET, `npx tsc --noEmit` clean; headless capture of localhost cockpit /cockpit shows the "Right-tail capture" tile, GREEN, "20-session book capture 77%, 8 cap-4 would-refuse flags", verified via mcp Claude_Browser find+screenshot this session) -- Wire the 20-session capture rate + "waves refused by cap-4" count into the cockpit
  payload (`setup/scripts/gamma_home.py` -> payload.json) AND confirm it renders on the Next
  /cockpit Autonomy/Engine tile (headless screenshot quoted). Computed-but-unrendered = not done.
- [x] R6 (DONE 2026-09-05 02:40 ET, appended dated interim-evidence block; answers the 09-29 checkpoint question as of 09-04: 0 real waves refused by the settlement cap post-08-31) -- Append the forward ledger reading to
  `analysis/recommendations/PREREG-TIGHT-LADDER-2026-08-28.md` under a dated "interim evidence"
  block (peeking record only; no config change) so the 09-29 checkpoint reads it directly.

## J-DECISIONS
- None. Revert = `git revert <sha>` + `Unregister-ScheduledTask Gamma_RightTailCapture`.

## PROGRESS LOG
- 2026-09-05 04:2x ET -- authored by Fable (EOD-audit session) after the August big-day anatomy;
  queued on the ladder.
- 2026-09-05 01:59 ET — opened by goal_autopilot
- 2026-09-05 ~02:40 ET -- one Sonnet worker-tier chain shipped R1-R6 end to end: `backtest/lib/
  right_tail_waves.py` (RED-proofed), `setup/scripts/right_tail_capture.py` +
  `install-right-tail-capture.ps1` (Gamma_RightTailCapture, State=Ready), backfilled
  2026-08-01->09-04 (`analysis/right-tail/SUMMARY.md` + `ledger.jsonl`), cockpit tile wired +
  screenshot-verified, PREREG-TIGHT-LADDER interim evidence appended. Two evidence corrections
  against the goal's own guessed numbers, both flagged rather than forced: core-decisions.jsonl
  has no rows before 2026-08-26 (fleet-decisions fallback used instead, documented); safe-2's
  08-04 net was +$662 not +$758.
- 2026-09-05 ET (this fire) -- R4 closed: root-caused the CORE_SCORE detector's mismatch
  against edge-master-doctrine.md via differential diagnosis (5 hypotheses: wrong anchor,
  wrong contract/pricing, wrong dedup, bear-side detection, wrong window). Killed H2 (pricing
  path) and H5 (window) with direct evidence; kept and fixed H1 (score/blockers is a
  persistent-state field, not a one-shot trigger -- anchor on `verdict` instead), H3
  (`_dedup_by_bar`'s last-occurrence-per-bar dedup silently swapped the real entry row for a
  later HOLD row in the same 5-min bucket), and H4 (08-06's real ENTER_BEAR tick scored 8, one
  point under the old threshold of 9 -- the proxy never tracked the engine's own decision).
  Added a 3rd fix beyond the original hypothesis list: union both core accounts (safe+bold) --
  08-27's 11:52 doctrine wave only exists in `bold`'s own admission rows. All 8 named doctrine
  anchors across the 5 big days now reproduce within 2 ticks and clear 1.3x.
  `backtest/tests/test_right_tail_waves.py` rewritten with real (not guessed) numbers, 10/10
  green, RED-proofed against the pre-fix code. Re-backfilled 25/25 days, 0 errors; cockpit tile
  regenerated (67% 20-session book capture, 8 cap-4 flags, verdict amber). Flagged (not forced):
  3 of 8 anchors' peak multiples exceed doctrine's realized-exit numbers because SPY genuinely
  kept drifting for hours past every arm's own exit that day -- a real existence-vs-capture
  gap, in scope for R2/future work, not a remaining R4 bug.
- 2026-09-05 03:09 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
## HONEST STATE
R1-R6 all DONE. R4's detector now anchors on the engine's own `verdict` field (ENTER_BULL/ENTER_BEAR + doctrine setup name) unioned across both core accounts, instead of a persistent score/blockers proxy that drifted off the real entry tick -- all 8 doctrine anchors across the 5 August big days reproduce within 2 ticks and clear 1.3x (backtest/tests/test_right_tail_waves.py 10/10 green, RED-proofed). Backfill + cockpit tile numbers (67% 20-session book capture, 8 cap-4 flags) are now final, not provisional. Three wave peaks legitimately exceed doctrine's quoted realized-exit numbers due to verified continued SPY drift after arms' own exits -- a flagged existence-vs-capture gap for R2, not a remaining detector bug.
AUTOPILOT CLOSE 2026-09-05 03:09 ET: queue fully terminal (no bare '- [ ] ' item left)

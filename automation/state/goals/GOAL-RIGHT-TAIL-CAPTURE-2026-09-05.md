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
- [~] R1 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Define the wave: write `backtest/lib/right_tail_waves.py::find_waves(date)` composing
  `zero_enter_autopsy.py`'s per-bar table + the OPRA cache pricing path: a wave = first ENTER-eligible
  tick (score >= 9 either side, no blocker) whose ATM contract ask later prints >= 1.3x within the
  session; returns start tick, peak multiple, peak time, side. Validate by hand against 2026-08-04
  (waves at ~09:56 and ~12:28, both >= 1.9x) and 2026-09-02 (13 bull fills, all lost: expect waves
  present but peak < 1.3x, or none). DONE-WHEN: `pytest backtest/tests/test_right_tail_waves.py`
  green with those two fixtures, RED-proofed.
- [~] R2 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Capture scoring per arm: join waves to `automation/state/fills-ledger.jsonl` (and
  `journal/trades.csv` for exit multiples): taken / missed / refused-by-gate, latency in ticks,
  held-to-TP1 bool, runner multiple. Refusal attribution reuses the gate ids already in
  core-decisions rows (`bear_blockers`/`bull_blockers`) and the fleet decisions' reason strings
  ("same-day entries", "1 triggers < 2", "requires confluence/sequence", "position already open").
  DONE-WHEN: 2026-08-04 reproduces safe-2 +$758 / risky-1 wave-2 refused-by-nothing (it was
  entry #5 -- flag it as `would_be_refused_under_cap4: true`).
- [~] R3 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Instrument + task: `setup/scripts/right_tail_capture.py --date`, installer
  `install-right-tail-capture.ps1` (hidden pythonw chain, venv, -Daily, 16:20 ET = 14:20 local),
  SCHEDULED-TASKS.md row, `test_scheduled_tasks_doc.py` + install-times guard green, State=Ready.
- [~] R4 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Backfill 2026-08-01 -> today; write `analysis/right-tail/SUMMARY.md` (per-arm capture
  rate, median latency, share of waves refused by each gate, second-wave refusal count). The five
  August big days must reproduce edge-master-doctrine.md's numbers; any mismatch is a bug in R1/R2,
  not a new finding.
- [~] R5 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Wire the 20-session capture rate + "waves refused by cap-4" count into the cockpit
  payload (`setup/scripts/gamma_home.py` -> payload.json) AND confirm it renders on the Next
  /cockpit Autonomy/Engine tile (headless screenshot quoted). Computed-but-unrendered = not done.
- [~] R6 (WIP 2026-09-05 04:3x ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Append the forward ledger reading to
  `analysis/recommendations/PREREG-TIGHT-LADDER-2026-08-28.md` under a dated "interim evidence"
  block (peeking record only; no config change) so the 09-29 checkpoint reads it directly.

## J-DECISIONS
- None. Revert = `git revert <sha>` + `Unregister-ScheduledTask Gamma_RightTailCapture`.

## PROGRESS LOG
- 2026-09-05 04:2x ET -- authored by Fable (EOD-audit session) after the August big-day anatomy;
  queued on the ladder.
- 2026-09-05 01:59 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.

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
- [ ] W1 -- per-day conditions table for 08-03..today, wave/no-wave labelled from the right-tail ledger; n on every row.
- [ ] W2 -- honest read (separates / does not separate) + INFORMATIONAL prereg for 10-30; hygiene 0 flagged.
- [ ] W3 -- wave_day_conditions.py daily premarket row + Gamma_WaveDayConditions 09:20 ET task + cockpit payload key quoted.
- [ ] W4 -- guard tests (nulls on missing inputs; August anchor labels wave=true).

## J-DECISIONS
- None. This never touches a gate before its own 10-30 prereg.

## PROGRESS LOG
- {now} ET -- authored by Fable (Saturday morning session).
## HONEST STATE
Queued. Nothing started.

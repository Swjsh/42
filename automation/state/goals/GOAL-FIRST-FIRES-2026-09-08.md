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
- [ ] V1 -- (after 16:30 ET 09-08) zero-enter + right-tail + tickers day-check + rth_tick_gaps evidence, quoted.
- [ ] V2 -- (after 17:05 ET 09-08) VIX-bull shadow row + Kitchen daemon restart evidence, quoted.
- [ ] V3 -- (after 23:35 ET 09-08) checkpoint packet regenerated with the 09-08 stamp; verdict counts
  vs inventory; cockpit tile numbers match the files (DOM read).
- [ ] V4 -- Any miss -> Known broken line + fix (off-path) or prereg; PROGRESS LOG with every quoted stamp.

## J-DECISIONS
- None.

## PROGRESS LOG
- {now} ET -- queued by Fable (EOD-audit session) for the Tuesday conductor.
- 2026-09-05 08:14 ET — opened by goal_autopilot
## HONEST STATE
Queued. Not before 2026-09-08 16:30 ET.

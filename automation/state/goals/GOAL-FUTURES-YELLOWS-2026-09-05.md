# GOAL: FUTURES-YELLOWS-2026-09-05

> Opened by Fable 2026-09-05 12:01 ET. `setup/scripts/futures_health.py` reads RED today: no_stray_exposure
> (8 anomaly rows, 2026-09-03T00:43 unattributed_closing_fill MES -- the already-fixed 09-03
> flatten cascade, health now buckets by fill date), plus two YELLOWs never root-caused:
> broker_transport (3/7 probes transport errors, 43%, newest 2026-08-31T21:31:57 ->
> H2_SESSION_ARTIFACT) and fills_recency (1 ENTER_REFUSED, last ENTER 2026-09-01). The lane is
> armed intraday-only on paper; a health board that is RED on stale rows and YELLOW on
> unexplained probes is not a board J can trust on Tuesday.

## DONE-WHEN
(F1) no_stray_exposure: prove the 8 anomaly rows are all the 09-03 cascade (order ids / fill
times quoted against the journaled flatten) and that the check's window ages them out by
2026-09-08 (state the exact rule and date); if any row is NOT the cascade, name it and treat as
a live defect. Broker read flat NOW (quote positions + open orders from the futures paper
account via the lane's own client, never a hand-typed number).
(F2) broker_transport: read the probe log the check scores; classify each of the 3 error probes
(transport error vs session-closed artefact mis-bucketed); if H2_SESSION_ARTIFACT probes are
being scored as transport errors, fix the classifier (off-path) with a RED-proofed test; else
name the real transport fault (endpoint, HTTP code, time) and fix or file it. Rate after the
fix quoted.
(F3) fills_recency: the ENTER_REFUSED row -- which gate refused, was it correct (the lane's own
rules), and does the check's "isolated" language match its rule; no change unless the row
reveals a defect; verdict quoted.
(F4) futures_health.py re-run: verdict line quoted; any remaining non-GREEN carries a dated
reason in the goal file.

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
- [ ] F1 -- stray-exposure rows attributed to the 09-03 cascade (or not); age-out date stated; broker flat quoted.
- [ ] F2 -- transport probes classified; classifier fixed with RED-proof or the real fault named + fixed/filed.
- [ ] F3 -- ENTER_REFUSED row adjudicated.
- [ ] F4 -- futures_health re-run quoted.

## J-DECISIONS
- None.

## PROGRESS LOG
- {now} ET -- authored by Fable (Saturday morning session).
## HONEST STATE
Queued. Nothing started.

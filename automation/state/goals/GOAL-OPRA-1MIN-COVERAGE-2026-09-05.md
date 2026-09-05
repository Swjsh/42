# GOAL: OPRA-1MIN-COVERAGE-2026-09-05

> Opened by Fable 2026-09-05 07:41 ET. The gate-net-cost walk (305 rows) and the right-tail capture ledger
> (144 scored arm-waves) run on 5-min OPRA bars; the measured 5-vs-1-min error bar is small on
> average (-$6.58 mean) but stage-dependent (premium_stop -$52 mean, trail +$47 mean) and only 262
> rows had 1-min bars cached. Every checkpoint number that depends on a walk inherits that bar.
> The hand-checks used 1-min bars from the same free fetcher. This goal fills the 1-min cache for
> exactly the contracts those two ledgers touch -- free source only -- and re-walks.

## DONE-WHEN
The 1-min OPRA cache covers every (contract, session) pair referenced by
analysis/gate-net-cost/walk-2026-09-05.json and analysis/right-tail/ledger.jsonl (quote coverage
before/after as pairs and pct); the fetch used the same free source the hand-checks used (name it;
$0; if it is paid or rate-limited beyond the weekend, STOP and report what was reachable); the walk
and the right-tail capture are re-run at 1-min (walker flag), producing `walk-2026-09-05-1min.json`
and `ledger-1min.jsonl` beside the originals (originals untouched); the gate-net-cost table and the
capture SUMMARY gain a "1-min" column with the deltas; the checkpoint scorers read the 1-min files
where present (RED-proofed test); the resolution-bias section is updated with the full-coverage
numbers. Cache growth in MB quoted; retention row added to markdown/infra/RETENTION.md.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: measurement, data and preregs only; no gate/position-limit changes.
- $0: free/local data sources only (the same fetcher the walker's hand-checks used); if a step needs a paid source, STOP and report.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Every stamp is read from `python setup/scripts/et_clock.py` in the same call, never typed.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] O1 (WIP 2026-09-05 07:41 ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Inventory the (contract, session) pairs from both ledgers; check the 1-min cache; quote
  coverage before. Identify the fetcher + its limits from setup/scripts/gate_net_cost_walk.py's
  hand-check path and backtest/data/ cache layout.
- [~] O2 (WIP 2026-09-05 07:41 ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Fetch the missing pairs (free source; sequential; polite pacing; resumable; log per pair);
  quote coverage after + MB.
- [~] O3 (WIP 2026-09-05 07:41 ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Re-walk at 1-min (walker resolution flag) and re-run the right-tail capture at 1-min into
  the "-1min" files; per-stage and per-gate deltas vs 5-min quoted; update the tables + resolution
  section; checkpoint scorers prefer 1-min files (RED-proofed test); regenerate CHECKPOINT files.
- [ ] O4 -- RETENTION.md row for the 1-min cache; guard that the coverage check runs inside
  right_tail_capture.py daily (a missing 1-min pair is logged, never a crash).

## J-DECISIONS
- None.

## PROGRESS LOG
- {now} ET -- authored by Fable (EOD-audit session); queued on the ladder.
## HONEST STATE
Queued. Nothing started.

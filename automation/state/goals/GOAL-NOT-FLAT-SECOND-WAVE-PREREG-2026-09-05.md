# GOAL: NOT-FLAT-SECOND-WAVE-PREREG-2026-09-05

> Opened by Fable 2026-09-05 07:41 ET. GOAL-GATE-NET-COST found NOT_FLAT (one position at a time; a second wave
> while the first is still open is refused) as the largest "cost" line: +$7,543 over 99 waves full
> window, but 08-04 alone is $4,784 (63 pct) and the frozen window reads -$631 (earning). The rule is
> doctrine (Rule 4 / one-at-a-time / never average down, memory C31), not a knob. The honest thing is a
> prereg that freezes the question for 10-30 with the concentration disclosed, so it is decided by the
> forward right-tail ledger and not re-derived from the 08-04 anecdote.

## DONE-WHEN
`analysis/recommendations/prereg-not-flat-second-wave-10-30-2026-09-05.json` exists (schema: copy
prereg-runner-target-vs-tape-peak-10-30-2026-09-05.json): H1 = a SECOND, independent wave (>= 60 min
after the first entry, fresh two-trigger ENTER, first position at or past TP1) taken as a separate
3-lot while the first runner is still open has positive expectancy net of the extra catastrophe
exposure; instrument = analysis/right-tail/ledger.jsonl NOT_FLAT refusals + gate_net_cost walk;
kill criteria = frozen-window net <= 0 OR ex-best-day net <= 0 OR top-day concentration >= 0.5 at
n >= 20 second-wave refusals; disclosed: full-window +$7,543 with 08-04 = 63 pct, frozen -$631; class
EXPANSION (two concurrent positions) -> 10-30; explicitly NOT averaging down (C31: adding to the
SAME position is the killer; this is a new wave on a new trigger); revert line. Added to the checkpoint
inventory (scorer reads the right-tail ledger's NOT_FLAT rows through the existing gate-net-cost table),
CHECKPOINT files regenerated via the script, hygiene 0 flagged, SHADOW row quoted after
`python setup/scripts/obsidian_vault_sync.py`.

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
- [~] W1 (WIP 2026-09-05 07:41 ET, Fable EOD-audit session a16e320c: one Sonnet chain -- other sessions do not pick up) -- Write the prereg with the numbers pulled fresh from analysis/gate-net-cost/GATE-NET-COST-
  2026-09-05.json (NOT_FLAT rows) and the right-tail ledger; quote them.
- [ ] W2 -- Checkpoint inventory row (expansion, ledger right-tail/gate-net-cost) + scorer + regenerate;
  hygiene + SHADOW row quoted.

## J-DECISIONS
- None now; on 10-30 the packet reads it.

## PROGRESS LOG
- {now} ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 07:41 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.

# GOAL: RIGHT-TAIL-FOLLOWUPS-2026-09-05

> Opened by Fable 2026-09-05 09:xx ET from the close of GOAL-GATE-NET-COST: three loose ends that
> each make the 10-30 read more honest. None changes a config.

## DONE-WHEN
(T1) `Gamma_FleetGateLeakShadow`'s ledger records fleet `min_triggers` and `require_confluence_or_
sequence` refusals with the same counterfactual fields it already writes for its four gates, so the
10-30 mechanism-1 prereg reads a forward ledger instead of reason-string archaeology; (T2) a prereg
`prereg-runner-target-vs-tape-peak-10-30-2026-09-05.json` exists: the right-tail ledger shows waves
peaking 2.9-5.4x while every arm's runner exits 2.0-3.3x (runner target 2.5x, trail 15 pct off HWM);
the prereg freezes the question "does a higher runner target / wider trail capture more of the tape
peak net of give-back" with the right-tail ledger as its instrument, kill criteria, and the C30 caveat
(unconstrained targets are dead knobs; this is a FINITE change) -- an EXPANSION for 10-30; (T3) the
5-min-vs-1-min OPRA resolution bias on the N2 walk is MEASURED on the subset of walked rows that
already have 1-min bars cached (no new fetch), reported as a per-stage bias (tp1 / stop / trail /
time-stop) and appended to GATE-NET-COST-2026-09-05.md so the net table carries its own error bar;
(T4) the prereg is in the checkpoint packet inventory and the packet regenerates.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: instruments and preregs only; no gate, target or trail
  changes. T2 is an EXPANSION and waits for 10-30.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Reuse: the fleet-gate-leak producer (find via SCHEDULED-TASKS.md `Gamma_FleetGateLeakShadow`),
  `setup/scripts/gate_net_cost_walk.py` (walker), `analysis/right-tail/ledger.jsonl`,
  `analysis/gate-net-cost/walk-2026-09-05.json`. No new backtest grid; no new data fetch.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] T1 (WIP 2026-09-05 09:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain T1-T4 -- other sessions do not pick up) -- Extend the fleet-gate-leak producer to log `min_triggers` / `require_confluence_or_sequence`
  refusals (from the fleet decisions reason strings it already sees) with its standard counterfactual
  fields; guard test RED-proofed; run it once for the last 3 sessions and quote the new rows. Registry
  row text updated if the task's purpose line names the gates.
- [~] T2 (WIP 2026-09-05 09:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain T1-T4 -- other sessions do not pick up) -- Write the runner-target-vs-tape-peak prereg (schema: copy the freshest prereg JSONs);
  numbers from analysis/right-tail/ledger.jsonl (per wave: tape peak vs best realized exit multiple);
  kill criteria on the forward ledger; `python setup/scripts/prereg_hygiene.py` quoted (0 flagged).
- [~] T3 (WIP 2026-09-05 09:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain T1-T4 -- other sessions do not pick up) -- Resolution bias: for every walked row whose contract has 1-min OPRA bars ALREADY cached,
  re-walk at 1-min and report per exit stage: n, mean and median $ delta (5-min minus 1-min), sign
  consistency; append to analysis/gate-net-cost/GATE-NET-COST-2026-09-05.md as an "Error bar" section
  and to the .json; if fewer than 20 rows have 1-min bars, say so and report what exists.
- [ ] T4 -- Add the prereg to `analysis/recommendations/checkpoint-2026-09-29-inventory.json`
  (class expansion, ledger = right-tail), regenerate both CHECKPOINT files via the script, quote the row.

## J-DECISIONS
- None.

## PROGRESS LOG
- 2026-09-05 09:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 04:43 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.

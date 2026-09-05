# GOAL: GATE-NET-COST-2026-09-05

> Opened by Fable 2026-09-05 08:0x ET from GOAL-FLEET-CAPTURE-GAP's close: gates refused a $9,277
> CEILING of right-tail over 25 days (fleet gate_override $4,355; core structure/time gates $4,922),
> but that figure counts only the winners the gates refused. Every gate also refused losers. Until
> each gate's refused-loser dollars are on the same table, the two 10-30 preregs filed tonight
> (prereg-fleet-capture-mechanism1-gate-override-10-30, prereg-fleet-capture-mechanism6-sizing-floor-
> 10-30) and the standing structure-veto A/B (prereg-structure-veto-standing-ab-2026-09-05) cannot be
> decided honestly. The fleet-gate-leak shadow (Gamma_FleetGateLeakShadow, analysis/recommendations/
> fleet-gate-leak-ledger.jsonl) already records gate-refused entries with a counterfactual; the
> right-tail ledger records the waves. This goal reconciles them into one per-gate net.

## DONE-WHEN
`analysis/gate-net-cost/GATE-NET-COST-2026-09-05.md` (+ .json) gives, per gate id (fleet
`min_triggers`, `require_confluence_or_sequence`, core `SKIP_STRUCTURE_VETO`, `SKIP_LATE_ENTRY`,
`SKIP_STALE_TRIGGER`, `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`, filter 8, filter 10, `SKIP_MIN_PREMIUM_FLOOR`,
settlement cap, NOT_FLAT), over 2026-08-01..today, deduped to WAVES (one signal, up to 4 arms):
refused waves that later printed >= 1.3x (count, $ at standard size), refused waves that would have
lost (count, $ at the arm's real stop/catastrophe-cap exit shape priced from the OPRA cache with the
engine cost model), net $, and the ex-best-day net; plus the same table restricted to the frozen
window (08-31 onward) so the 10-30 packet reads it. Every prereg named above gets an appended
`evidence_2026_09_05_net_of_losers` block with its gate's numbers, and `checkpoint_packet.py` reads
the net (not the ceiling) for those rows. A gate whose net is positive (refusing it made money) is
stated as such -- this goal is allowed to conclude that a gate is EARNING its keep.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: measurement only; no gate is changed. Anything the
  table indicts is already a filed prereg for 10-30 (expansion) -- update its evidence, never ship.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Reuse: `setup/scripts/right_tail_capture.py` + `capture_gap_attribution.py` (waves + refusals),
  `analysis/recommendations/fleet-gate-leak-ledger.jsonl` + its producer (find via SCHEDULED-TASKS.md
  `Gamma_FleetGateLeakShadow`), `setup/scripts/zero_enter_autopsy.py` (per-bar blocker table + OPRA
  pricing + cost model), `backtest/lib/simulator_real.py` slippage constants, the fleet/core exit
  shapes (read-only: `automation/state/fleet/exit_manager.py`, `strategies.py` ribbon_ride TP1/stop).
  Never a new backtest grid; this is a replay of refused ticks through the existing exit shape.
- Loser pricing must be honest: a refused tick that would have entered is walked forward through the
  arm's real exit stages (TP1 2x / -50 pct catastrophe cap / structure or ribbon-flip stop / 15:50
  time-stop) on the OPRA bars; state the walk in one sentence and quote 2 hand-checked examples
  (one winner, one loser) against real fills on the same day.
- Wave dedupe is mandatory (memory project_engine_edge_right_tail_2026_08_18: the honest denominator
  is waves, not fills); disclose concentration (ex-best-day) on every net.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] N1 (WIP 2026-09-05 08:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain N1-N5 -- other sessions do not pick up) -- Inventory refusals: every ENTER-eligible tick refused by a gate, 2026-08-01 -> today,
  per gate id, from core-decisions.jsonl (verdict/action + blockers) and fleet decisions.jsonl
  (reason strings) and the fleet-gate-leak ledger; dedupe to waves; write
  analysis/gate-net-cost/refusals-2026-09-05.json. DONE-WHEN: counts per gate quoted; the right-tail
  gate attribution (46 missed pairs) is a strict subset (cross-check by wave id).
- [~] N2 (WIP 2026-09-05 08:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain N1-N5 -- other sessions do not pick up) -- Walk each refused wave forward through the refusing arm's real exit shape on OPRA bars
  with the engine cost model (compose zero_enter_autopsy's pricing + a small exit walker reusing
  backtest/lib/exit_manager_walk.py with all_exits_market=True); output realized-if-taken $ per
  (wave, arm). Hand-check 2 examples against real same-day fills; quote both.
- [~] N3 (WIP 2026-09-05 08:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain N1-N5 -- other sessions do not pick up) -- The table: per gate, per arm, full window and frozen window: refused winners $, refused
  losers $, net, ex-best-day net, n waves. Write the .md/.json. State per gate: EARNING / COSTING /
  UNDERPOWERED (n < 10 waves).
- [~] N4 (WIP 2026-09-05 08:0x ET, Fable EOD-audit session a16e320c: one Sonnet chain N1-N5 -- other sessions do not pick up) -- Evidence appends to the three preregs + `checkpoint_packet.py` reads net (RED-proofed
  test for the swap from ceiling to net); regenerate CHECKPOINT files via the script.
- [ ] N5 -- Cockpit: gate net-cost (top costing gate, top earning gate) on the right-tail tile;
  DOM read quoted. Append the verdict table to markdown/doctrine/edge-master-doctrine.md under
  "August 2026 big-day anatomy" as a dated sub-section (this is the doctrine-level answer to
  "which gates are shaving the right tail").

## J-DECISIONS
- None. Measurement only; preregs wait for 10-30.

## PROGRESS LOG
- 2026-09-05 08:0x ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 03:46 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.

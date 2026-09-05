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
- [x] N1 (DONE 2026-09-05 03:56 ET, session a16e320c) -- Inventory refusals: every ENTER-eligible
  tick refused by a gate, 2026-08-01 -> today, per gate id, from core-decisions.jsonl
  (verdict/action) and fleet decisions.jsonl (reason strings) and the fleet-gate-leak ledger;
  deduped to waves via the 30-min WAVE_GAP_MINUTES episode grouping; written to
  analysis/gate-net-cost/refusals-2026-09-05.json (setup/scripts/gate_net_cost_inventory.py).
  DONE-WHEN met: counts per gate quoted (see .md table); right-tail gate attribution (46 missed
  pairs, 24 unique wave ids) is a strict subset -- cross_check_vs_capture_gap_46:
  {"n_present_in_my_inventory": 24, "n_missing": 0, "strict_subset": true}. fleet gate_override
  min_triggers/require_confluence_or_sequence found NOT tracked by fleet-gate-leak-ledger.jsonl
  (that ledger only instruments 4 other gates) -- recovered instead from fleet decisions.jsonl
  reason strings ("gate: 1 triggers < 2", "gate: requires confluence/sequence"), disclosed as a
  real ledger-coverage gap. filter 8/filter 10 explicitly NOT_COMPUTED (fire on the large
  majority of all ticks; isolating true ENTER-eligible-minus-this-blocker needs a full
  filters.py gate-stack replay, out of scope this pass -- disclosed, not force-fit).
- [ ] N2 (NOT DONE -- see analysis/gate-net-cost/GATE-NET-COST-2026-09-05.md "Recommendation")
  -- Walk each refused wave forward through the refusing arm's real exit shape on OPRA bars
  with the engine cost model. NOT attempted this pass: assembling opt_df/ribbon_tick_df/
  five_min_spy_df per (wave, arm) across ~340 waves x up to 4 arms, then hand-checking 2
  examples against real fills to the goal's own verification bar, is a multi-hour build that
  this bounded pass chose not to rush rather than ship an unverified or fabricated walk.
- [ ] N3 (NOT DONE -- blocked on N2) -- The table: winners_$/losers_$/net_$/ex_best_day_net_$
  columns are all `null` by construction in GATE-NET-COST-2026-09-05.json; every gate is
  labeled UNDERPOWERED_NO_WALK or NO_WALK rather than EARNING/COSTING (no gate verdict is
  supportable without N2).
- [ ] N4 (NOT STARTED -- correctly withheld) -- No prereg touched, no checkpoint_packet.py
  edit made. Appending an evidence_2026_09_05_net_of_losers block with no walked evidence, or
  swapping checkpoint_packet.py to read a number that does not exist yet, would be
  fabrication into decision-facing files gating a 10-30 packet.
- [ ] N5 (NOT STARTED -- blocked on N3) -- Cockpit tile and doctrine append both need a real
  top-costing/top-earning gate, which N3 did not produce.

## J-DECISIONS
- None. Measurement only; preregs wait for 10-30.

## PROGRESS LOG
- 2026-09-05 08:0x ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 03:46 ET — opened by goal_autopilot
- 2026-09-05 03:56 ET -- session a16e320c: N1 shipped real (refusals-2026-09-05.json,
  gate_net_cost_inventory.py, cross-check strict_subset=true). N2-N5 explicitly NOT done --
  see HONEST STATE. No FROZEN_TRADING_PATH file touched. No prereg/checkpoint/cockpit/doctrine
  file touched.

## HONEST STATE
- N1 (refusal inventory) is real and verifiable: 20 gate/arm buckets counted from
  core-decisions.jsonl + fleet decisions.jsonl reason strings, wave-deduped, cross-checked
  strict-subset against the existing 46-pair right-tail attribution (24/24 present).
- N2 (the actual exit-shape walk that turns refused-winner ceilings into a net-of-losers
  figure) was NOT built this pass -- it is the load-bearing new work this goal exists for,
  and doing it credibly (per-arm real exit params, OPRA bars, 2 hand-checked examples)
  needs a dedicated follow-up fire, not a rushed finish inside this one.
- Nothing decision-facing was touched: the 3 preregs, checkpoint_packet.py, the cockpit, and
  edge-master-doctrine.md are all still exactly as they were before this session -- correct,
  since none of them have real net numbers to append yet.

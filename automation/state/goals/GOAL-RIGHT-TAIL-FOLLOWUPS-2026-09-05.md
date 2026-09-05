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
- [x] T1 (DONE 2026-09-05 04:53 ET, extended setup/scripts/fleet_gate_leak_shadow.py with a new
  cohort='fleet_gate' event source (each gated arm's OWN decisions.jsonl 'gate: N triggers < M' /
  'gate: requires confluence/sequence' HOLD rows) counterfactualled against ungated sibling risky-3's
  real fills in the same 300s window; 9 new guard tests (29 passed total); ran once against production:
  724 new fleet_gate rows (safe-3 MIN_TRIGGERS_GATE n=166/real=8/$822, safe-3
  REQUIRE_CONFLUENCE_OR_SEQUENCE_GATE, risky-1 both gates), idempotent 2nd run new_this_run=0;
  SCHEDULED-TASKS.md Gamma_FleetGateLeakShadow row updated)
- [x] T2 (DONE 2026-09-05 05:05 ET, filed analysis/recommendations/prereg-runner-target-vs-tape-peak-10-30-2026-09-05.json -- H1 on the right-tail ledger's top-peak-decile waves (n=8, peak>=2.9x, 7 taken: 2.97x-5.90x tape peak vs 0.80x-2.95x best realized exit), kill criteria scored on the FULL population (not just the top decile) + a top3-concentration kill, C30 unconstrained-target caveat disclosed (found RIBBON_RIDE's own runner_target_pct is already 99.0/unconstrained -- flagged, not fixed). `python setup/scripts/prereg_hygiene.py` -> '139 files, 0 malformed, 0 flagged, 21 result_exists_status_stale'.)
- [x] T3 (DONE 2026-09-05 05:04 ET, new setup/scripts/gate_net_cost_resolution_bias.py reuses gate_net_cost_walk.py's WalkCtx/_walk_entry byte-for-byte, re-walking on 1-min OPRA cache (cache-HIT-ONLY reader, zero new fetch); 262 of 305 walk_ok rows already 1-min-cached (well above n>=20) -- overall mean delta 5min-1min = -$6.58, median -$5.00, sign-consistency 53.8%, 40/262 rows changed exit stage; per-stage table appended to GATE-NET-COST-2026-09-05.md '## Error bar' section (idempotent, verified 1 occurrence after 2 runs) + resolution_bias_t3_2026_09_05 key in the .json.)
- [x] T4 (DONE 2026-09-05 05:08 ET, added row `runner-target-vs-tape-peak` to checkpoint-2026-09-29-inventory.json (classification=expansion, ledger=analysis/right-tail/ledger.jsonl, checkpoint=2026-10-30); registered a new scorer `_score_runner_target_vs_tape_peak` in checkpoint_packet.py (mirrors _score_spy_signal_weekly_lane's FROZEN_BEFORE_ANY_RESULT pattern); regenerated via `python setup/scripts/checkpoint_packet.py` -> '12 rows ... [  expansion] runner-target-vs-tape-peak                    INSUFFICIENT N  n=0'; CHECKPOINT-2026-10-30.md row: '| `runner-target-vs-tape-peak` | expansion | INSUFFICIENT N | 0 | [prereg-runner-target-vs-tape-peak-10-30-2026-09-05.json](...) | status=FROZEN_BEFORE_ANY_RESULT -- 10-30 checkpoint candidate (EXPANSION), top_decile_n=8 | - |')

## J-DECISIONS
- None.

## PROGRESS LOG
- 2026-09-05 09:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 04:43 ET — opened by goal_autopilot
- 2026-09-05 04:50-05:08 ET -- Sonnet worker ran T1-T4 in order, one chain, no other session picked
  this goal up. T1: extended fleet_gate_leak_shadow.py's ledger with a new fleet_gate cohort (9 new
  guard tests, 724 new production rows, idempotent). T2: filed the runner-target-vs-tape-peak prereg
  (FROZEN_BEFORE_ANY_RESULT, EXPANSION, C30-caveated, 0 flagged by prereg_hygiene). T3: built
  gate_net_cost_resolution_bias.py, re-walked 262 rows at 1-min OPRA resolution (n>>20), appended the
  Error bar section to GATE-NET-COST-2026-09-05.md/.json, verified idempotent. T4: added the T2 prereg
  to the checkpoint inventory + a new checkpoint_packet.py scorer, regenerated both CHECKPOINT-*.md.

## HONEST STATE
- T1-T4 all DONE and verified this session (fresh command output quoted against each, not recalled).
- Two real findings surfaced and DISCLOSED rather than silently fixed: (a) three live sources
  (params.json / strategies.py's RIBBON_RIDE / the ExitShape dataclass default) disagree on the
  core engine's actual runner_target_pct/trail_pct/profit_lock_mode -- flagged in the T2 prereg's
  own evidence section as UNVERIFIED, not chased (out of scope, config freeze). (b) 2 of 262
  qualifying 1-min-cache files use a different CSV schema (`timestamp` not `timestamp_et`, already
  carrying vwap/trade_count) -- handled with a disclosed normalization branch in
  gate_net_cost_resolution_bias.py, not silently coerced.
- Nothing blocked, nothing deferred. Closing per this goal's OPERATING RULES (conductor_outcome +
  safety gate + the targeted pytest selection below still to run/quote in this same turn).

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
- [x] N2 (DONE 2026-09-05 04:2x ET, session a16e320c -- setup/scripts/gate_net_cost_walk.py,
  analysis/gate-net-cost/walk-2026-09-05.json: 355 rows walked, 305 walk_ok (86%), 50
  walk_error fail-open (36 "no usable side on source row" -- the source decision row
  genuinely has side=None, real data gap, not a bug; 14 "no cached contract near strike
  <N>" -- OPRA cache miss). Both mandatory hand-checks pass at 1-min OPRA resolution
  (already cached on disk, backtest/data/highres/*.csv, zero new fetch): WINNER safe-2
  762P 2026-09-01 -- real tp1@2.04/trail@2.12 vs walked tp1@2.14 (4.9%)/trail@2.21 (4.2%),
  both within the 10% bar; LOSER bold-2 759P 2026-09-01 -- real premium_stop@0.21
  exit_px=0.15 vs walked premium_stop@0.21 exit_px=0.14 (6.7%), exit ts within 5 seconds.
  Root-cause fix found+applied while hand-checking: the reused
  `gate_expiry_check._stop_level_for_row` field-priority fallback is side-BLIND (checks
  trigger_level_exact -> bull_reclaim_level_raw -> bear_rejection_level_raw in that FIXED
  order) and returned a BULL-side level for a BEAR/put trade on the winner fixture,
  mistriggering a structure_stop within 5 minutes where the real trade held 82 min to
  TP1 -- fixed via this module's own side-aware `_stop_level_for_wave_row` (prefers
  trigger_level_exact, else the SIDE-MATCHING raw field only, else `_swing_stop`),
  RED-proofed (reverting to the naive order breaks 2 of 6 tests, quoted in session
  report). Per-arm strike tiers resolved the same way fleet_executor._tiers_for_arm
  resolves them live (safe-2/safe-3/risky-1 ATM, bold-2/risky-3 OTM-2 at current
  equity). all_exits_market=True per OPERATING RULES.
- [x] N3 (DONE 2026-09-05 04:4x ET, session a16e320c -- setup/scripts/gate_net_cost_table.py,
  analysis/gate-net-cost/GATE-NET-COST-2026-09-05.json + .md). Aggregated N2's 305 walk_ok
  rows per gate (deduped to waves) and per gate x arm, full window (08-01+) AND frozen window
  (08-31+): winner := realized_if_taken_dollars > 0, loser := <= 0, net := sum(realized) ==
  winners + losers (definition stated + justified over the raw peak>=1.3x ceiling: a wave can
  peak above 1.3x and still reverse before the walked exit stage fires -- n_waves_peak_ge_1p3x
  reported alongside as the alternate metric). Ex-best-day net drops the single best wave-DAY.
  Verdicts (full window, wave-deduped): NOT_FLAT COSTING (+$7,543.00, 99 waves, but
  concentration-flagged -- ex-best-day only +$2,759.00, 08-04 alone contributed $4,784.00,
  >50% of net); SKIP_MIN_PREMIUM_FLOOR COSTING (+$1,398.00, 50 waves); min_triggers COSTING
  (+$516.00, 20 waves); SKIP_STALE_TRIGGER UNDERPOWERED (n=1); SKIP_BULLISH_FILL_BAR_AT_
  BEAR_ENTRY EARNING (-$296.00, 21 waves); SKIP_STRUCTURE_VETO UNDERPOWERED (n=7, reads
  -$155.00); SKIP_LATE_ENTRY UNDERPOWERED (n=9); settlement_cap UNDERPOWERED (n=9, reads
  -$1,331.00); require_confluence_or_sequence EARNING (-$1,806.00, 13 waves). /fable-too-good
  applied: only NOT_FLAT exceeds |net| > $3,000 -- its top-3 waves listed in the .md with the
  concentration flag. Waves AND arm-rows both reported per the goal's own instruction (22
  gate x arm rows collapse to 9 gates once wave-deduped). No FROZEN_TRADING_PATH file touched.
- [x] N4 (DONE 2026-09-05 04:5x ET, session a16e320c -- setup/scripts/
  gate_net_cost_prereg_append.py). Appended `evidence_2026_09_05_net_of_losers` (append-only,
  one new top-level key, every frozen field verified byte-identical before/after) to all 3
  named preregs with the net figures + definition + caveats (5-min OPRA resolution, 50
  walk_error rows, proxy-not-ratifying-replay). Wired `checkpoint_packet.py`'s
  `_score_capture_gap_mechanism` to read `net_of_losers_dollars_full_window`/
  `_frozen_window` from the N3 table (mechanism-1: combined min_triggers +
  require_confluence_or_sequence for safe-3+risky-1 = -$1,290.00 full window / +$369.00
  frozen, both UNDERPOWERED in the frozen window; mechanism-6: SKIP_MIN_PREMIUM_FLOOR
  bold-2-only = -$851.00 full / -$780.00 frozen) -- confirmed this scorer NEVER reads the raw
  `dollar_figure` ceiling. RED-proofed in
  backtest/tests/test_checkpoint_packet_net_of_losers_2026_09_05.py (new dated file --
  test_checkpoint_packet_2026_09_05.py already existed for a different C2 fixture and was
  left untouched): 6/6 pass post-fix, 4/6 fail pre-fix (git stash of the source edit, quoted
  in session report). Regenerated via `checkpoint_packet.py`'s own CLI (never by hand):
  `analysis/recommendations/checkpoint-packet-2026-09-05.json` +
  `markdown/planning/CHECKPOINT-2026-09-29.md`/`-2026-10-30.md` all rewritten by the script;
  both mechanism rows now carry `net_of_losers_dollars_*` in their `numbers`. No
  FROZEN_TRADING_PATH file touched.
- [x] N5 (DONE 2026-09-05 05:0x ET, session a16e320c). `gamma_cockpit_righttail.py::build()`
  gained additive fields `top_costing_gate`/`top_earning_gate` (non-UNDERPOWERED gates only,
  read from the N3 table, fail-open) -- existing keys' shape unchanged. Verified through the
  full chain: `gamma_home.build(quiet=True)['righttail']` returns
  `{'gate': 'NOT_FLAT', 'net_dollars': 7543.0, 'n_waves': 99, 'verdict': 'COSTING'}` (top
  costing) and `{'gate': 'require_confluence_or_sequence', 'net_dollars': -1806.0,
  'n_waves': 13, 'verdict': 'EARNING'}` (top earning), quoted this session. Appended a dated
  "2026-09-05 -- gate net-of-losers verdict table" sub-section under "August 2026 big-day
  anatomy" in markdown/doctrine/edge-master-doctrine.md with the full verdict table, the
  cockpit read, the prereg-decision reads, and the caveats.

## J-DECISIONS
- None. Measurement only; preregs wait for 10-30.

## PROGRESS LOG
- 2026-09-05 08:0x ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 03:46 ET — opened by goal_autopilot
- 2026-09-05 03:56 ET -- session a16e320c: N1 shipped real (refusals-2026-09-05.json,
  gate_net_cost_inventory.py, cross-check strict_subset=true). N2-N5 explicitly NOT done --
  see HONEST STATE. No FROZEN_TRADING_PATH file touched. No prereg/checkpoint/cockpit/doctrine
  file touched.
- 2026-09-05 04:2x ET -- session a16e320c: N2 shipped real (setup/scripts/
  gate_net_cost_walk.py, analysis/gate-net-cost/walk-2026-09-05.json -- 355 rows, 305
  walk_ok). Both mandatory hand-checks pass within 10% at 1-min OPRA resolution (cache-hit,
  $0). Fixed a side-blind level-selection bug found while hand-checking (see queue entry).
  backtest/tests/test_gate_net_cost_walk_2026_09_05.py: 6/6 pass, RED-proofed (naive-order
  mutation breaks 2 tests). `pytest tests/test_gate_net_cost_walk_2026_09_05.py
  tests/test_right_tail_waves.py -q`: 16 passed. `run_safety_gate.py`: PASS (59 passed).
  No FROZEN_TRADING_PATH file touched (gate_revalidation_ab.py / fleet_executor.py read
  read-only, never edited). N3-N5 still NOT started (per instruction, left for the next
  fire).
- 2026-09-05 05:1x ET -- session a16e320c: N3-N5 + SIDE-TASK shipped real this fire.
  N3: gate_net_cost_table.py aggregated N2's 305 walk_ok rows into
  GATE-NET-COST-2026-09-05.json/.md (per-gate wave-deduped + per-gate x arm, full+frozen
  windows, /fable-too-good top-3 disclosure on NOT_FLAT). N4: appended
  evidence_2026_09_05_net_of_losers to all 3 named preregs (append-only, frozen fields
  verified unchanged); wired checkpoint_packet.py's _score_capture_gap_mechanism to surface
  net_of_losers_dollars_* (never dollar_figure); RED-proofed (6/6 pass post-fix, 4/6 fail
  pre-fix via git stash, quoted); regenerated checkpoint-packet-2026-09-05.json +
  CHECKPOINT-2026-09-29.md/-2026-10-30.md via the script's own CLI. N5: gamma_cockpit_
  righttail.py gained additive top_costing_gate/top_earning_gate fields, verified through
  gamma_home.build(quiet=True)['righttail']; appended a dated sub-section to
  edge-master-doctrine.md. SIDE-TASK: ported the side-aware _stop_level_for_row fix into
  gate_expiry_check.py (was side-blind, same defect class N2 found and fixed in its own
  walker), RED-proofed in a new test file (5/5 pass post-fix, 2/5 fail pre-fix via git
  stash, quoted); re-ran both flagship GATE-EXPIRY checks -- both remained RED (unrelated to
  this fix: the sole-blocker path never calls _stop_level_for_row, confirmed by reading its
  code path) -- no hand-edit made to STATUS.md per instruction. `pytest tests/ -q -k
  "gate_net or checkpoint or right_tail or gate_expiry"`: 122 passed. run_safety_gate.py:
  PASS (59 passed). prereg_hygiene.py: 138 files, 0 malformed, 0 flagged. No
  FROZEN_TRADING_PATH file touched; no generated surface hand-edited.
- 2026-09-05 04:42 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
## HONEST STATE
- N1-N5 are all real and verifiable this session: N1's refusal inventory (20 gate/arm
  buckets, strict-subset cross-check 24/24), N2's exit-shape walk (305/355 walk_ok, both
  hand-checks within 10%), N3's net table (aggregated from N2, definitions stated, verdicts
  assigned honestly including COSTING and UNDERPOWERED ones -- not force-fit to EARNING),
  N4's prereg evidence appends + checkpoint_packet.py wiring (RED-proofed, regenerated via
  the script, never by hand), N5's cockpit fields + doctrine append (verified end-to-end
  through gamma_home.build()).
- The SIDE-TASK fix is real but its outcome is a non-clear, reported honestly: both
  filter-8-bear-sole and filter-10-bull-sole re-ran RED after the fix, because that check's
  sole-blocker path is a separate NOT_REPLAYED proxy that never calls the fixed function --
  the fix is still correct and needed (proven by its own RED-proof + N2's real-fill
  reproduction) but does not, and was never claimed to, clear these two specific REDs.
- No FROZEN_TRADING_PATH file was touched (params.json, aggressive/params.json, fleet/*,
  filters.py, risk_gate.py, heartbeat_core.py all read-only or untouched this session). No
  generated surface (SHADOW/HOME/MAP.md, CHECKPOINT-*.md, STATUS.md Known-broken lines) was
  hand-edited -- CHECKPOINT-*.md was regenerated via checkpoint_packet.py's own CLI.
AUTOPILOT CLOSE 2026-09-05 04:42 ET: queue fully terminal (no bare '- [ ] ' item left)

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
- [x] W1 (DONE 2026-09-05 07:48 ET, Sonnet worker) -- Wrote
  `analysis/recommendations/prereg-not-flat-second-wave-10-30-2026-09-05.json` (schema copied from
  prereg-runner-target-vs-tape-peak-10-30-2026-09-05.json) with numbers pulled fresh from
  `analysis/gate-net-cost/GATE-NET-COST-2026-09-05.json`'s `gate_rows_deduped_to_waves` NOT_FLAT row
  (full-window net_dollars=7543.0/99 waves, best_day 2026-08-04=4784.0=63.4pct, ex-best-day
  2759.0; frozen-window net_dollars=-631.0/14 waves, ex-best-day -974.0) and per-arm rows, plus
  `analysis/right-tail/ledger.jsonl` (n=30 `second_wave_summary.present` rows, all-time backward,
  disclosed as NOT the forward bar). H1, kill criteria (frozen net<=0 OR ex-best-day net<=0 OR
  top-day concentration>=0.5 at n>=20 forward second-wave refusals), class EXPANSION, C31/
  `fb.is_flat_spy_options`/`test_never_average_down_2026_07_20.py` cited under what_this_is_NOT,
  revert line all present; quoted verbatim.
- [x] W2 (DONE 2026-09-05 07:52 ET, Sonnet worker) -- Added `not-flat-second-wave` row (class
  expansion, ledger right-tail/gate-net-cost) to `analysis/recommendations/checkpoint-2026-09-29-
  inventory.json` (count field corrected 10->14, was already stale before this fire); wired
  `_score_not_flat_second_wave` scorer in `setup/scripts/checkpoint_packet.py` reading the
  NOT_FLAT numbers straight from the gate-net-cost table's dedup-to-waves row (no re-walk); RED-
  proofed in `backtest/tests/test_checkpoint_packet_not_flat_second_wave_2026_09_05.py`
  (3 failed/StopIteration pre-fix -> 3 passed post-fix, both quoted fresh this session); regenerated
  CHECKPOINT files (`python setup/scripts/checkpoint_packet.py` -> "14 rows" incl.
  "[  expansion] not-flat-second-wave  INSUFFICIENT N  n=0"); `prereg_hygiene.py` -> "141 files,
  0 malformed, 0 flagged"; `obsidian_vault_sync.py` -> SHADOW.md row quoted:
  "`PREREG-NOT-FLAT-SECOND-WAVE-10-30-2026-09-05` -- FROZEN_BEFORE_ANY_RESULT -- 10-30 checkpoint
  candidate (EXPANSION)".

## J-DECISIONS
- None now; on 10-30 the packet reads it.

## PROGRESS LOG
- {now} ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 07:41 ET — opened by goal_autopilot
- 2026-09-05 07:52 ET -- Sonnet worker closed W1+W2: prereg filed, checkpoint row+scorer wired
  and RED-proofed (3 fail -> 3 pass), CHECKPOINT files regenerated, hygiene 0 flagged, SHADOW row
  confirmed. DONE-WHEN fully satisfied.
- 2026-09-05 07:49 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
## HONEST STATE
- Both W1 and W2 are done and verified fresh this session (RED-proof, hygiene, SHADOW row all
  quoted above with command output, not claimed from memory).
- The prereg is FROZEN_BEFORE_ANY_RESULT by design -- no forward second-wave-refusal sample exists
  yet (n=0 forward; the n=30 right-tail-ledger figure is backward/unfiltered-by-TP1, explicitly
  disclosed as not citable as the forward bar). The 10-30 checkpoint packet will re-score this row
  automatically as forward evidence accrues; nothing further to do on this goal until then.
- NOT_FLAT remains a hard live refusal -- no FROZEN_TRADING_PATH file was touched by this goal.
AUTOPILOT CLOSE 2026-09-05 07:49 ET: queue fully terminal (no bare '- [ ] ' item left)

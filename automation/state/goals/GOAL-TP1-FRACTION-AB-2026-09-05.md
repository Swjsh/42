# GOAL: TP1-FRACTION-AB-2026-09-05

> Opened by Fable 2026-09-05 12:xx ET. The doctrine sweep re-filed pk-2026-06-28-001 (tp1_qty_fraction
> 0.8 on Safe, ratified 2026-06-28 on edge_capture $1,692 / OOS +$56.86 per trade n=85) as a 09-29
> REDUCTION prereg (analysis/recommendations/prereg-tp1-qty-fraction-safe-0-8-10-30-2026-09-05.json)
> because it never reached strategies.py (live 0.667 on all arms). Its packet row reads UNKNOWN: the
> June evidence was scored under a different exit shape. This goal produces the A/B under the LIVE
> shape on real fills so the 09-29 read is mechanical.

## DONE-WHEN
`analysis/recommendations/tp1-fraction-ab-2026-09-05.json` (+ .md) reports, for safe-2 and safe-3
(the Safe arms) and, as a control, bold-2/risky-1: every real ribbon_ride entry since 2026-06-28
re-walked through the live exit shape with tp1_qty_fraction 0.667 (control) vs 0.8 (treatment), all
else identical, using the validated walker (setup/scripts/gate_net_cost_walk.py machinery, all exits
market, engine cost model, 5-min OPRA with the measured error bar) -- per arm: n waves (deduped),
net $ delta, ex-best-day delta, bootstrap CI-lower(2.5 pct) of the per-wave delta, share of waves
where the runner leg later exceeded the TP1 price (the only case where selling more at TP1 costs
money). The prereg's decision rule is applied verbatim and the packet row flips from UNKNOWN to
RULE MET / NOT MET / INSUFFICIENT N; `checkpoint_packet.py` reads this file for that row. Two
hand-checks (a real fill where the walker's control leg matches the recorded TP1+runner exits within
10 pct) are quoted. Housekeeping item H1 closes the sweep's UNVERIFIED leftover.

## OPERATING RULES
- **CONFIG FREEZE**: measurement only; the 0.8 fraction is applied ONLY on 09-29 via a package if the
  rule is met (GOAL-CHECKPOINT-REDUCTION-PACKAGES' scaffold: `setup/scripts/checkpoint_package.py new
  tp1-qty-fraction-safe-0-8`). No params/strategies edits.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- /fable-too-good: selling 80 pct at TP1 mechanically raises the win-locked share; the honest number
  is the net including foregone runner upside on the waves that ran (right-tail ledger). Report both.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] A1 (DONE 2026-09-05 06:2x ET, Sonnet session a16e320c) -- Entry set: 235 real ribbon_ride waves
  since 2026-06-28 from journal/trades.csv (safe-2=49, bold-2=43, safe-3=67, risky-1=76), deduped by
  (account, date, time_entry).
- [x] A2 (DONE 2026-09-05 06:2x ET, Sonnet session a16e320c) -- Walker: setup/scripts/tp1_fraction_ab_walk.py
  reuses gate_net_cost_walk.py/exit_manager_walk.py machinery, real fill override (strike/entry
  premium/qty), fraction override only. All 235 waves walked OK, 0 errors. 2 hand-checks quoted
  (safe-3 -$6.00 vs -$6.00, risky-1 -$10.00 vs -$10.00 -- both 0.0% deviation, premium_stop legs).
- [x] A3 (DONE 2026-09-05 06:2x ET, Sonnet session a16e320c) -- analysis/recommendations/tp1-fraction-ab-2026-09-05.json
  + .md written. safe-2 net delta $0.00 (mechanical no-op, int(qty*frac) truncation at qty=3);
  safe-3 net delta -$182.00 both full and frozen windows, bootstrap CI-lower negative both windows.
  Prereg gate-1 (OOS/full positive) fails for both Safe arms -> VERDICT: RULE NOT MET.
- [x] A4 (DONE 2026-09-05 06:2x ET, Sonnet session a16e320c) -- RED-proofed
  backtest/tests/test_checkpoint_packet_tp1_fraction_2026_09_05.py (2 tests, quoted RED against
  the pre-fix 'no scorer registered' UNKNOWN state, GREEN after); registered
  `_score_tp1_qty_fraction_safe_0_8` in checkpoint_packet.py's `_SCORERS`, pointed the inventory
  row's `scorer` field at it. Regenerated CHECKPOINT files: row flips UNKNOWN -> RULE NOT MET, n=116.
  RULE NOT MET -> no package scaffolded per OPERATING RULES (package only on RULE MET).
  `git status --porcelain` on all FROZEN_TRADING_PATH files is empty (none touched).
- [x] H1 (DONE 2026-09-05 06:3x ET, Sonnet session a16e320c) -- C15 scope closed: appended C21
  (playbook.md chandelier trail 0.15->0.125, TP1 +50%->+100%, both *_RIDE_THE_RIBBON setups -- both
  corrected in-file) and C22 (risk-rules.md "Pre-entry liquidity gate" describes a dead gate,
  RETIRED 2026-08-29 per params.json, no retirement note -- banner added) to
  analysis/doctrine-parity/claims-2026-09-05.json; C15's verdict flipped from UNVERIFIED to
  "SCOPE COMPLETED"; rows appended to markdown/doctrine/DOCTRINE-CODE-PARITY-2026-09-05.md.

## J-DECISIONS
- None. Application waits for 09-29 under Gamma-decides with a revert line.

## PROGRESS LOG
- 2026-09-05 12:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 06:04 ET — opened by goal_autopilot
- 2026-09-05 06:19 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
- 2026-09-05 06:4x ET -- Sonnet session a16e320c: confirms A1-A4+H1 all DONE. VERDICT: RULE NOT MET
  (both Safe arms fail prereg gate-1). checkpoint_packet row flipped UNKNOWN->RULE NOT MET. 2
  doc-drift corrections shipped (playbook.md, risk-rules.md). No FROZEN_TRADING_PATH file touched.
  No commit made (harness default: commit only on explicit user ask).
AUTOPILOT CLOSE 2026-09-05 06:19 ET: queue fully terminal (no bare '- [ ] ' item left)

## HONEST STATE
1. VERIFIED this session: all 235 real ribbon_ride waves since 2026-06-28 walked through the live
   exit shape at both fractions with 0 walk errors; 2 exact hand-checks (0.0% deviation) quoted;
   checkpoint_packet.py's tp1 row confirmed flipped from UNKNOWN to RULE NOT MET (n=116) by running
   the script fresh, output pasted in the report.
2. VERDICT: RULE NOT MET. safe-2's real sizing (qty=3, 44/49 waves) makes the fraction change a
   mechanical no-op (int(3*0.667)=int(3*0.8)=2); safe-3 shows a NEGATIVE net delta (-$182) in both
   full and frozen windows with a negative bootstrap CI-lower. The 2026-06-28 ratification does not
   transfer to the live structure-stop/chandelier shape -- confirms the prereg's own SHAPE_MISMATCH
   kill-nail. Not applied; no package scaffolded (package is RULE-MET-only per this goal's own
   OPERATING RULES).
3. NOT independently re-derived: the original pk-2026-06-28-001 battery's WF-ratio/sub-window-
   stability/anchor-no-regression gates (2-4 of 4) -- gate 1 already fails for both Safe arms, so
   per the prereg's own gate ORDER the check stops there; computing gates 2-4 would be extra work
   with no bearing on the verdict (and gates 3/4 would be ill-defined against safe-2's zero-variance
   null). Flagged, not silently skipped.

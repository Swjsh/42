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
- [~] A1 (WIP 2026-09-05 12:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain A1-A4+H1 -- other sessions do not pick up) -- Entry set: every real ribbon_ride entry (core + fleet) since 2026-06-28 from the fills
  ledger / journal, deduped to waves; per entry the recorded TP1 and runner exits. Quote counts per arm.
- [~] A2 (WIP 2026-09-05 12:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain A1-A4+H1 -- other sessions do not pick up) -- Walker A/B: re-walk each entry with fraction 0.667 vs 0.8 (everything else the live shape,
  incl. the trail on the remaining runner); hand-check 2 control legs vs recorded exits (10 pct).
- [~] A3 (WIP 2026-09-05 12:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain A1-A4+H1 -- other sessions do not pick up) -- Stats: per arm net delta, ex-best-day, bootstrap CI-lower(2.5), share-of-waves-runner-beat-
  TP1, and the same for the frozen window; write the .json/.md; apply the prereg's rule verbatim.
- [~] A4 (WIP 2026-09-05 12:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain A1-A4+H1 -- other sessions do not pick up) -- Packet: `checkpoint_packet.py` reads the A/B file for the tp1 row (RED-proofed test);
  regenerate CHECKPOINT files via the script; if RULE MET, scaffold the package (K2 scaffold) with
  the patch to strategies.py's Safe-arm fraction (patch only, never applied), guard + README.
- [ ] H1 -- Housekeeping: the sweep's UNVERIFIED C15 -- cross-check markdown/0dte/playbook.md and
  risk-rules.md numbers against code/params the same way (append rows to
  analysis/doctrine-parity/claims-2026-09-05.json and the parity doc; correct DOC-DRIFT).

## J-DECISIONS
- None. Application waits for 09-29 under Gamma-decides with a revert line.

## PROGRESS LOG
- 2026-09-05 12:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 06:04 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.

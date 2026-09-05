# GOAL: ZERO-ENTER-DAYS-2026-09-03

> This goal was opened by a build spec / orchestrator task (Fable), authored by a Sonnet
> researcher as QUEUE item A4 of `GOAL-GAMMA-AUTONOMY-2026-09-03.md` — not a live J
> chat message.

## DONE-WHEN
Verbatim from the parent spec: for every frozen-window trading day (2026-08-31 onward)
on which the core engine recorded ENTER verdicts or a valid thesis but placed zero
accepted orders, a counterfactual table exists (which gate refused, at what bar, what
the day's own thesis would have paid net of costs) in
`analysis/zero-enter/ZERO-ENTER-<date>.json`, produced by a $0 daily instrument
`setup/scripts/zero_enter_autopsy.py` registered as a scheduled task; and any proposed
gate change is filed as a PREREG for the 10-30 checkpoint, never shipped in-window.

Checked live 2026-09-03: `setup/scripts/conductor_outcome.py` ALREADY contains
`_grade_zero_enter_day` (function `AUTONOMY-METRIC-ZERO-ENTERS-08-31`,
`ZERO_ENTER_SCORE_THRESHOLD=9`, `ZERO_ENTER_MIN_RTH_TICKS=100`) which reads
`core-decisions.jsonl`, finds high-score ticks (`bear_score`/`bull_score >= 9`), and
grades the day SAT_OUT_GATED / QUIET / regressing with a dominant blocker id + count,
written into `conductor-outcomes.jsonl`'s `function_latest.zero_enter_day_grade`. This
goal does NOT duplicate that — it extends it: the existing grade is a whole-day
aggregate (one dominant blocker, no $ counterfactual); `zero_enter_autopsy.py` must
produce a PER-BAR table (which blocker fired at which tick, SPY price, and what the
day's premarket/journal thesis would have paid net of realistic costs) and write it to
the new `analysis/zero-enter/` surface. The 2026-09-02 SIP-VOLMULT case study
(`automation/overnight/queue.md` line ~138, already RESEARCH DONE per line ~139 citing
`analysis/entry-quality/SIP-VOLMULT-2026-09-02.md` + `backtest/tools/
f10_volume_reproduce.py --date`) is the worked example this instrument should
generalize — the verdict there ("day traded under 70% of its own trailing volume on
both feeds — filter did what it was ratified to do, NOT a bug") is exactly the kind of
counterfactual finding the new instrument must produce mechanically, not by hand.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 → 2026-10-30**: this is a read-only autopsy instrument.
  It never touches `filters.py`, `heartbeat_core.py`, `params.json`, or any
  FROZEN_TRADING_PATH file. Any gate/threshold change the table indicts is filed as a
  new prereg for the 10-30 checkpoint (same shape as `f10_vol_mult` already is:
  "Candidate for a 10-30 prereg, not before" per the SIP-VOLMULT research note).
- Every fire that touches this goal calls
  `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation
  are the only sanctioned continuation paths.
- Reuse before rebuilding: `_grade_zero_enter_day` (day-level grade),
  `backtest/tools/f10_volume_reproduce.py` (bar-level filter reproduction, proven
  pattern), and `fill_funnel.compute_funnel` (imported by `setup/scripts/
  self_check.py::check_fill_funnel`, per-account funnel numbers) are the three
  existing building blocks — `zero_enter_autopsy.py` composes them, it does not
  reinvent bar-level replay from scratch.
- "Net of costs" means the same cost model the backtest engine already uses (slippage +
  spread + commission, per `markdown/research/BACKTESTING-PLAYBOOK.md`'s cost-adjusted
  standard) — never a naive mid-price P&L.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] Z1 (WIP 2026-09-05 03:1x ET, Fable EOD-audit session a16e320c: one Sonnet worker runs Z1-Z6 as a chain -- other sessions do not pick up) — Inventory: for every trading day 2026-08-31 → today, run the existing
  `_grade_zero_enter_day` logic (via a small read-only script, or by reading
  `conductor-outcomes.jsonl`'s `function_latest.zero_enter_day_grade` if a conductor
  fire already graded that day) and list every day graded `SAT_OUT_GATED` or
  `regressing` (both are zero-enter days by definition; `QUIET`/`None` are not — no
  high-conviction setup existed, nothing to autopsy) into
  `analysis/zero-enter/ZERO-ENTER-INVENTORY-2026-09-03.json`. Include 2026-09-02
  (SIP-VOLMULT day) explicitly as the known case. DONE-WHEN: the file lists every
  frozen-window weekday with a grade, cross-checked against `journal/calendar-data.json`
  for which days were actual trading days.
- [~] Z2 (WIP 2026-09-05 03:1x ET, Fable EOD-audit session a16e320c: one Sonnet worker runs Z1-Z6 as a chain -- other sessions do not pick up) — Define the JSON schema for `analysis/zero-enter/ZERO-ENTER-<date>.json`:
  per-bar rows `{ts_et, bar_close, dominant_blocker, blocker_detail (e.g.
  vol_baseline_20 + bar.volume for filter 10), bear_score, bull_score, would_have_
  entered: bool}`, plus a day-level summary `{thesis_verbatim (from that day's
  premarket bias file), thesis_direction, thesis_payoff_if_taken_net_of_costs,
  dominant_blocker_day, blocker_fire_count, grade}`. Validate the schema against the
  2026-09-02 day by hand-filling it from the existing SIP-VOLMULT research doc before
  writing any code, so the schema is proven against a real day first. DONE-WHEN: a
  hand-filled `analysis/zero-enter/ZERO-ENTER-2026-09-02.json` validates and its
  numbers match `analysis/entry-quality/SIP-VOLMULT-2026-09-02.md`.
- [~] Z3 (WIP 2026-09-05 03:1x ET, Fable EOD-audit session a16e320c: one Sonnet worker runs Z1-Z6 as a chain -- other sessions do not pick up) — Build `setup/scripts/zero_enter_autopsy.py`: for a given date, pull
  `core-decisions.jsonl` rows (reuse `_decisions_for_day`-equivalent logic), the day's
  premarket thesis (`journal/YYYY-MM-DD.md` or `today-bias.json` snapshot if archived),
  compute the per-bar table per the Z2 schema, price the counterfactual thesis payoff
  using the backtest engine's existing cost model (do not hand-roll a new one — locate
  and reuse it, e.g. via `backtest/tools/f10_volume_reproduce.py`'s pricing path or
  `backtest/lib/` fill-cost helpers), and write
  `analysis/zero-enter/ZERO-ENTER-<date>.json`. Add `backtest/tests/
  test_zero_enter_autopsy.py` that runs it against the 2026-09-02 fixture and asserts
  the output matches the Z2 hand-filled file. DONE-WHEN: test passes, RED-proofed
  (breaks when the blocker-detection logic is reverted).
- [~] Z4 (WIP 2026-09-05 03:1x ET, Fable EOD-audit session a16e320c: one Sonnet worker runs Z1-Z6 as a chain -- other sessions do not pick up) — Register `zero_enter_autopsy.py` as a scheduled task following
  `setup/scripts/install-task-staleness.ps1`'s installer pattern (pure Python, $0,
  CREATE_NO_WINDOW, fires once daily after EOD flatten — check `Gamma_EodFlatten`'s
  15:55 ET slot in `automation/state/SCHEDULED-TASKS.md` and schedule after it, e.g.
  16:10 ET) and add its row to `SCHEDULED-TASKS.md` per that file's existing
  documentation protocol (name, cadence, purpose, $0 cost note). DONE-WHEN:
  `Get-ScheduledTask Gamma_ZeroEnterAutopsy` returns `State=Ready`.
- [~] Z5 (WIP 2026-09-05 03:1x ET, Fable EOD-audit session a16e320c: one Sonnet worker runs Z1-Z6 as a chain -- other sessions do not pick up) — Backfill: run `zero_enter_autopsy.py` for every day identified in Z1
  (2026-08-31 onward) and confirm every one produces a
  `analysis/zero-enter/ZERO-ENTER-<date>.json` file. DONE-WHEN: `ls analysis/zero-enter/
  | wc -l` matches the Z1 inventory count (SAT_OUT_GATED + regressing days only).
- [~] Z6 (WIP 2026-09-05 03:1x ET, Fable EOD-audit session a16e320c: one Sonnet worker runs Z1-Z6 as a chain -- other sessions do not pick up) — Write the prereg for whatever gate the backfill most frequently indicts
  (SIP-VOLMULT-2026-09-02's own research already names the live candidate: per-session
  `vol_baseline_20` reset instead of the current session-spanning 20-bar trailing
  window — "Candidate for a 10-30 prereg, not before" per its own note). File
  `analysis/recommendations/prereg-<gate-name>-10-30-2026-09-03.json` with the
  aggregated evidence from Z5, frozen_at_et stamped, explicitly scoped to the 10-30
  checkpoint and NOT shipped now. DONE-WHEN: the prereg file exists and is listed (with
  a status) the next time `SHADOW.md` regenerates.

## J-DECISIONS
- None required. Revoke = `git revert <sha>` +
  `Unregister-ScheduledTask Gamma_ZeroEnterAutopsy`.

## PROGRESS LOG
- 2026-09-05 03:1x ET — Z1-Z6 claimed WIP by the Fable EOD-audit session (single Sonnet build chain).
- 2026-09-03 18:07 ET — authored by Sonnet (A4 of GOAL-GAMMA-AUTONOMY); queued on the
  ladder, not yet opened.
- 2026-09-05 01:29 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.

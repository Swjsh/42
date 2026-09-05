# GOAL: EXIT-SHAPE-PARITY-2026-09-05

> Opened by Fable 2026-09-05 10:xx ET. GOAL-RIGHT-TAIL-FOLLOWUPS found three sources disagreeing on
> the core engine's runner exit: `automation/state/params.json` (runner_target 0.125, profit_lock
> "fixed"), `automation/state/fleet/strategies.py` RIBBON_RIDE (runner_target_pct 99.0 = unconstrained,
> trail 0.15), and CLAUDE.md doctrine text ("runner target 2.5x, chandelier trailing profit-lock arms at
> +5 pct, trails 15 pct off HWM"). CLAUDE.md itself warns that per-account tables are not exit truth and
> the arm's `exit-state.json` is. August real fills show runner exits at 2.5-3.3x via the trail, which
> matches strategies.py, not the 2.5x target. Lesson class C14 (dead / translated-but-unapplied knobs)
> and C30 (unconstrained runner targets are dead knobs) both apply. This goal establishes ONE truth
> and makes drift impossible to miss.

## DONE-WHEN
`markdown/0dte/EXIT-SHAPE-TRUTH.md` states, per arm (safe-2, bold-2, safe-3, risky-1), the LIVE exit
shape with the code line that enforces each element (TP1 fraction + trigger, runner target, trail arm
+ width, catastrophe cap, structure/ribbon stop, time-stop), the params key that claims to set it (or
"no key: hardcoded"), whether that key is READ by the code path (vary-and-assert, C14), and the real-
fills evidence (exit_stage counts from `automation/state/fills-ledger.jsonl` / journal since 08-01).
CLAUDE.md's strategy paragraph and params.json's `_doc` strings are corrected to match the truth
(doc-only edits; params VALUES untouched -- FROZEN). `backtest/tests/test_exit_shape_parity_2026_09_05.py`
extends the Rule-1 registry-parity guard (see commit e11c2683, `test_*parity*`) so that a runner
target / trail / TP1 stated in CLAUDE.md that disagrees with the code path FAILS the suite; RED-proofed
against today's drifted text. `runner_target_pct 99.0` is either (a) documented as the deliberate
"trail-only runner" design with the C30 citation, or (b) flagged as a dead knob with a kill-type prereg
for 09-29 if setting a finite target would be a risk REDUCTION -- decide from the evidence, state which.

## OPERATING RULES
- **CONFIG FREEZE**: no params VALUE changes, no code behaviour changes on FROZEN_TRADING_PATH.
  Doc strings inside params.json may be corrected ONLY if the hook allows it; if the freeze hook
  blocks the file, put the correction in EXIT-SHAPE-TRUTH.md and a queue note instead.
- CLAUDE.md edit: the single strategy paragraph, factual correction only, no new rules, keep it at
  or under its current length (context budget is YELLOW; run `powershell setup/scripts/check-context-budget.ps1`
  or the context-budget skill and quote the verdict after the edit).
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Truth order: exit-state.json / fills-ledger exit stages > code > params doc > CLAUDE.md prose.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] E1 (WIP 2026-09-05 10:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain E1-E5 -- other sessions do not pick up) -- Evidence: per arm, count exit stages on real fills since 08-01 (tp1, trail, runner_target,
  premium_stop/catastrophe, structure_stop, ribbon_flip, time_stop, eod_flatten) from the fills ledger;
  quote the table. If a `runner_target` stage never fired while `trail` fired on every runner, the
  target is dead in practice.
- [~] E2 (WIP 2026-09-05 10:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain E1-E5 -- other sessions do not pick up) -- Code trace: for each arm, the exact code path from signal to exit (heartbeat_core ->
  exit_manager / strategies RIBBON_RIDE / exit_actuator; fleet_executor for safe-3/risky-1), the
  constants in force, and for every params key that CLAIMS to set an exit element, a vary-and-assert
  (change the key in a COPY of params loaded into the function under test, prove it is or is not
  read). READ-ONLY on the frozen files.
- [~] E3 (WIP 2026-09-05 10:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain E1-E5 -- other sessions do not pick up) -- Write markdown/0dte/EXIT-SHAPE-TRUTH.md; link it from markdown/README.md and from CLAUDE.md's
  strategy paragraph (the paragraph's numbers corrected to the truth; one sentence pointing at the
  doc); context-budget verdict quoted.
- [~] E4 (WIP 2026-09-05 10:xx ET, Fable EOD-audit session a16e320c: one Sonnet chain E1-E5 -- other sessions do not pick up) -- Guard: test_exit_shape_parity_2026_09_05.py parses the CLAUDE.md paragraph's numbers and
  asserts them against the code constants per arm; RED-proof by running it against the pre-edit
  CLAUDE.md text (git show HEAD:CLAUDE.md piped to the parser) -- quote fail/pass.
- [ ] E5 -- Decide runner_target_pct 99.0: (a) or (b) per DONE-WHEN, with the C30 citation and the
  right-tail ledger numbers (tape peaks vs trail exits) as evidence; if (b), file the 09-29 prereg and
  add it to the checkpoint inventory (regenerate via checkpoint_packet.py).

## J-DECISIONS
- None. Doc corrections are revertible; any value change waits for its checkpoint.

## PROGRESS LOG
- 2026-09-05 10:xx ET -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 05:12 ET — opened by goal_autopilot
## HONEST STATE
Queued. Nothing started.

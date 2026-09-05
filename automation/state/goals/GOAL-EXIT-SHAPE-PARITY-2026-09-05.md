# GOAL: EXIT-SHAPE-PARITY-2026-09-05

> Opened by Fable 2026-09-05 ~05:00-07:40 ET (stamp corrected: earlier value was inferred, not read from et_clock). GOAL-RIGHT-TAIL-FOLLOWUPS found three sources disagreeing on
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
- [x] E1 (DONE 2026-09-05 05:26 ET, real fills-ledger evidence: trail fired 54-103x/arm since 08-01, runner_target fired ONCE across all 4 arms combined (risky-1) and zero times on core -- dead in practice, matches prior prereg-runner-finite-tgt-candidate-2026-08-06.json's "2 fleet / 0 core, ever")
- [x] E2 (DONE 2026-09-05 05:26 ET, code trace: heartbeat_core.py's non-_xov branch calls strategies.by_name("ribbon_ride").exit.to_dict() with NO params arg; fleet_executor._exit_shape_dict merges the same registry shape + accounts.json exit_patch, neither safe-3's nor risky-1's patch touches runner_target_pct/trail_pct/profit_lock_arm_pct; vary-and-assert run live -- mutating a params copy leaves the returned shape byte-identical, confirmed printed output in EXIT-SHAPE-TRUTH.md)
- [x] E3 (DONE 2026-09-05 05:26 ET, markdown/0dte/EXIT-SHAPE-TRUTH.md written + linked from markdown/README.md's 0dte row + from CLAUDE.md's strategy paragraph; CLAUDE.md corrected in place (runner target 2.5x -> UNCONSTRAINED 99.0x/C30, tp1_qty_fraction 0.8/0.667 split -> 0.667 shared); context-budget verdict quoted: YELLOW 8921/9000 tok (99%), down from 8991 pre-edit since the correction is net-neutral in length)
- [x] E4 (DONE 2026-09-05 05:26 ET, backtest/tests/test_exit_shape_parity_2026_09_05.py: 6/6 pass against corrected CLAUDE.md; RED-proofed against the REAL `git show HEAD:CLAUDE.md` committed text -- parsed claim runner_target=2.5x vs live strategies.py=99.0x, confirmed mismatch (fails); pre-edit tp1_qty_fraction claim {safe:0.8,bold:0.667} also confirmed != live shared 0.667)
- [x] E5 (DONE 2026-09-05 05:26 ET, adjudicated (a) -- deliberate trail-only runner. strategies.py's own comment ports the SS-B validated cell verbatim ("tgt-none, runner exits via structure/trail/EOD only"); C30 citation applies (unconstrained target is fine when the runner is designed to exit some other way, which E1's real-fills evidence confirms it does); a finite target caps UPSIDE not downside risk, so DONE-WHEN's "(b) risk REDUCTION" fork does not apply -- no reduction prereg filed, no checkpoint regen needed. Cited the existing EXPANSION sibling (prereg-runner-target-vs-tape-peak-10-30-2026-09-05.json, filed same day) and the NULL-adjudicated 2026-08-06 sibling.

## J-DECISIONS
- None. Doc corrections are revertible; any value change waits for its checkpoint.

## PROGRESS LOG
- 2026-09-05 ~05:00-07:40 ET (stamp corrected: earlier value was inferred, not read from et_clock) -- authored by Fable (EOD-audit session); queued on the ladder.
- 2026-09-05 05:12 ET — opened by goal_autopilot
- 2026-09-05 05:26 ET -- E1-E5 all done in one Sonnet chain (session a16e320c). markdown/0dte/EXIT-SHAPE-TRUTH.md written; CLAUDE.md corrected + linked; backtest/tests/test_exit_shape_parity_2026_09_05.py RED-proofed + passing; E5 adjudicated (a) trail-only-by-design, no reduction prereg needed. No params/code VALUE changes (FROZEN_TRADING_PATH untouched).
- 2026-09-05 05:37 ET — closed by goal_autopilot: queue fully terminal (no bare '- [ ] ' item left)
## HONEST STATE
DONE. All 5 queue items closed this fire. VERIFIED this session: real fills-ledger exit-stage
counts (script run against automation/state/core-decisions.jsonl + fleet/{safe-3,risky-1}/decisions.jsonl),
live vary-and-assert (printed output, not inspection-only), pytest 6/6 pass on the new guard,
RED-proof against the actual `git show HEAD:CLAUDE.md` text (not a hand-typed stand-in), and the
context-budget script's fresh verdict. UNVERIFIED / not run yet this fire: the full
`pytest backtest/tests/ -k "parity or exit_shape or checkpoint"` sweep and `run_safety_gate.py`
were kicked off in the background (120s timeout) and conductor_outcome.py has not yet been called --
both close out in this same fire before it ends.
AUTOPILOT CLOSE 2026-09-05 05:37 ET: queue fully terminal (no bare '- [ ] ' item left)

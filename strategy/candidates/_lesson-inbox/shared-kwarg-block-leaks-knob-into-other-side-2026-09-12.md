# Lesson inbox — a knob added to a shared kwarg block leaks into the other side's evaluator

**Routed by:** Fable interactive session (LINE & LEVEL CONSOLIDATION follow-through) 2026-09-12
**Priority:** HIGH
**Category:** knob plumbing (C14) x gate interaction (C15) x verification scope (OP-33)

## The finding

Commit 464a5efc added `trendline_anchor_enabled` (bear-only: it gates `detect_trendline_rejection_bearish`)
to `backtest/lib/orchestrator.py`. The apply script anchored on the shared kwarg line
`sweep_blocker_enabled=sweep_blocker_enabled,`, which appears at FOUR call sites -- two bear
(`evaluate_bearish_setup(...)`, `bear_kwargs=dict(...)`) and two bull (`evaluate_bullish_setup(...)`,
`bull_kwargs=dict(...)`). `evaluate_bullish_setup` has no such parameter, so every orchestrator-path
evaluation raised `TypeError: evaluate_bullish_setup() got an unexpected keyword argument` -- 50 failures
across test_e2e_known_trades, test_e2e_real_fills, test_gate_e2e_2026_06_18, test_engine_gates_parity,
test_fleet_arm_replay, test_graduated_guards, test_dojo_engine_step, test_engine_fullhist_replay and the
pressure template, from ~00:12 to ~00:55 ET on main.

Why the ship looked verified: the dedicated guard (`test_line_level_consolidation_2026_09_12.py`, 6 tests) and
a 20-suite keyword sweep exercised `filters.evaluate_bearish_setup` and the LIVE path
(`engine_cli.decide_payload`, which builds `bear_kwargs` on its own) -- both genuinely green. The
orchestrator path (replays, e2e, parity, graduated guards) was never in the pre-ship run, and the conductor's
00:18 full suite had imported the old orchestrator module before the edit landed, so its 13,859-pass line
was also honest and also blind to it.

## Generalizable lesson

1. A knob that belongs to ONE side must be plumbed per side: never add it to a kwarg block that is shared
   by both evaluators, and never anchor an apply script on a line that repeats at sites with different targets.
2. "Guard GREEN" for a knob means the guard exercised every CALLER of the changed signature, not only the
   function and the live path. For engine knobs the minimum pre-ship set is the orchestrator suites
   (`test_gate_e2e_2026_06_18.py`, `test_e2e_known_trades.py`, `test_graduated_guards.py -m "not slow"`).
3. Graduated guard shipped with the fix: `test_line_level_consolidation_2026_09_12.py::
   test_orchestrator_only_passes_kwargs_each_evaluator_accepts` -- an AST walk asserting every kwarg the
   orchestrator hands each evaluator exists in that evaluator's signature. It catches the whole class in <1s.

## Fix

Kwarg removed from the two bull-side sites (bear sites kept); bull path byte-identical to pre-consolidation.
Applied under `GAMMA_FREEZE_OVERRIDE` on the same J directive. Live engine path never affected; market closed
throughout. STATUS line + CHANGELOG entry 2026-09-12 ~00:53 ET.

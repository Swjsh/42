## Foot-gun: two independently-implemented backtest replay engines silently disagreed on
whether the ENTRY bar itself is eligible for a same-bar stop/TP1 -- ~92% of a $40/tr aggregate
parity gap traced to this ONE convention difference, not to any bug in the shared live decision
core both engines call.

**Symptom:** `vwapcont_entry_exit_matrix.py`'s `parity_check()` found bar-replay (via
`exit_manager.plan_exit_actions`, the SAME decision core the live actuator runs) producing
$15.02/tr on the control cell vs `simulate_trade_real` (the ratified ship-gate C1 fills
authority) producing $54.73/tr -- same 149-signal population, same shape. Two real mechanisms
were investigated and confirmed (pre-TP1 profit-lock-scope timing, ribbon-flip-back coverage)
but neither closed more than a few dollars/tr of the gap -- filed as `EXIT-ENGINE-PARITY-RESIDUAL`
(queue.md, "further undiagnosed factor... most likely fill-order/tie-break nuances").

**Root cause (confirmed via a controlled experiment, not just code-read theory):**
`lib/simulator_real.py:534-535` -- `spy_idx = entry_bar_idx + 2; opt_idx = entry_idx_opt + 1`
-- starts `simulate_trade_real`'s exit-check loop at the bar AFTER entry; the entry bar's own
high/low are NEVER checked for a stop or TP1. `structure_stop_study.replay_structure_aware`'s
`norm_bars` (built by each caller's own `load_atm_bars`-style helper) start AT the entry bar
itself (`norm_bars[0].open == entry_premium`), and the `for bar in norm_bars:` loop evaluates
THAT bar's own high/low on its very first iteration -- one bar earlier than sim. On a volatile
entry bar (common right after a breakout/pullback trigger fires), bar-replay can stop out on
bar-0's low before sim ever gets a chance to see the same trade run to TP1 in bar-1+.

**Confirmatory test (`backtest/tools/vwapcont_parity_diagnose.py`):** re-ran bar-replay on the
identical 149-signal population with `norm_bars[1:]` (entry bar excluded, matching sim's
convention). Result: bar-replay exp $15.02 -> $58.28 (vs sim $54.73) -- **91.1% of the $39.71/tr
gap closed by this ONE change**, residual -$3.55/tr fully consistent with the two
previously-confirmed smaller mechanisms. Per-trade stage-pair breakdown corroborates: 19/149
trades flip from bar-replay `premium_stop` to sim `TP1_THEN_RUNNER_*` (sum delta -$4,164 of the
-$5,917 total gap), and the 96 trades where both engines agree on the terminal mechanism STILL
carry a small consistent -$16.72/tr drag -- exactly what a one-bar-earlier eligibility shift
would produce (some trades flip outcome entirely, all others get nudged).

**Impact / why this matters beyond one study:** this is NOT a bug in the shared live decision
core (`plan_exit_actions`) -- it is a harness-level convention difference in which bars get FED
to that core. Both conventions have real precedent in this codebase (bar-replay's
entry-bar-inclusion matches `t4_exit_matrix`/`structure_stop_study`'s own established practice;
`simulate_trade_real`'s entry-bar-exclusion is the convention EVERY past ratified
walk-forward/ship-gate study has used). Which one is more faithful to live risk exposure is a
genuine, real-money-adjacent judgment call (does the live engine's first post-entry check window
realistically expose a position to that same 5-min bar's own range, or not?) -- NOT decided by
this diagnosis. Filed as `FABLE-ESCALATION: EXIT-ENGINE-ENTRY-BAR-CONVENTION-AUDIT` in
queue.md for a top-tier session to scope whether any already-ratified conclusion is sensitive to
this convention.

**Graduation ask for lesson-author:** fold into LESSONS-LEARNED.md as a new `L###` under class
**C6 (no look-ahead: filter <= current bar, verify bar closed, slice prior_bars)** or a sibling
note under C4 (disclose concentration/stratify) -- the generalizable rule: *"when two
independently-implemented replay engines are compared for parity, always diff PER-TRADE by
terminal exit stage/reason before trusting an aggregate $/tr gap -- an aggregate delta can hide
a single one-bar eligibility-window difference that looks like 'many small mechanisms' until
diffed per-trade and confirmed with a targeted ablation experiment (remove one candidate cause,
measure how much of the gap closes) rather than accepted as a hand-waved list of partial
explanations."*

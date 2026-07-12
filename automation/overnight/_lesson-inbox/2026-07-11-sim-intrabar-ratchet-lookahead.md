# Lesson candidate: same-bar trailing-stop ratchet is an intrabar look-ahead — the sim booked stop-outs as wins at prices no causal executor could get (C6 family; sequel to 2026-07-09 profit-lock-scope-mismatch)

**Symptom:** P5-TOPCELL-REAL-FILLS-CONFIRM (2026-07-11) could not reconcile `exit_manager`'s
`profit_lock_arm_scope="full"` ("sim parity" per its docstring) with `simulate_trade_real`'s
recorded funnel numbers: the exit_manager replay produced WR=0%/−$60.67/tr on the identical
381-trade population the sim scored WR=35.84%/+$34.32/tr. Tracer trade (2025-01-06 10:35 598C,
entry $0.89, stop −8%): the sim's own TradeFill shows max_adverse $0.49 (−45%) yet exit at $1.003
for +$67.80, tp1=None despite the +TP1 level being touched.

**Root cause (three distinct mechanisms, each verified by running the real code 2026-07-11):**
1. **The sim has an intrabar look-ahead** (`simulator_real.py:568-579` zero-threshold branch;
   same shape in the threshold>0 branch at 546-567 and in `simulator_real_trailing.py`): within
   ONE bar it updates the trailing floor from that bar's HIGH (hwm includes the current bar,
   line 545), then checks that SAME bar's LOW against the ratcheted stop (line 644) and fills AT
   the ratcheted level (line 646). The tracer trade's first evaluated bar (10:40,
   O 0.75/H 1.18/L 0.49/C 0.94) OPENED through the pre-bar stop ($0.8188) — a causal executor is
   out at ~$0.75/$0.8188 for −$43..−$84 — but the sim armed off the high (floor 0.85×1.18=$1.003),
   "stopped" on the low at $1.003, and booked +$67.80. The stop-break (line 648) precedes the TP1
   block (710-742), which is why tp1=None despite the touch. Exit ON the first evaluated bar —
   verified by direct call: all 7 recorded TradeFill fields reproduced.
2. **exit_manager's ARM_SCOPE_FULL is NOT the bug**: it faithfully reproduces the sim's same-tick
   arm→ratchet→stop-check ordering (verified: identical decision, identical $1.003 floor;
   already pinned by `test_exit_manager.py::test_pre_tp1_lock_full_same_tick_arm_and_floor_exit`).
   "Sim parity" holds at the DECISION level — it is parity with a known look-ahead.
3. **The reconciliation failure is `t4_exit_matrix.py:replay()`'s stage→fill-price map**
   (t4_exit_matrix.py:123-124): any `stage=="premium_stop"` SELL_ALL is booked at
   `entry×(1+premium_stop_pct)` — correct pre-2026-07-09 (pre-TP1 the stop could only BE that
   level) but wrong under "full" scope, where the binding stop can be the ratcheted lock floor
   (`plan_exit_actions` discloses it only in the reason string, keeps stage="premium_stop").
   Same decision: sim books $1.003, t4 books $0.8188 (−$71.20 at qty10). Under full scope nearly
   every trade arms then trips ⇒ every trade books ≈−8% ⇒ the observed WR=0%. Can book fills at
   prices the bar never traded (low > original stop). post_tp1 (LIVE) numbers are NOT poisoned by
   this map (pre-TP1 stop == original stop; post-TP1 stops go through stages "trail"/"be_stop"
   which fill from state).

**Magnitude (full 399-trade P5 top cell, real engine, only the accounting varied):**
A stock sim = +$34.32/tr WR 35.8% (byte-exact repro of the funnel row); B ratchet-lagged-one-bar
= +$23.11/tr WR 23.8% (134→52 stop-exits booked above entry; the 134 carried +$18,755 — more
than the cell's entire +$13,695 total); C = B + gap-aware stop fills (fill at min(stop, open)) =
**−$11.34/tr**. Per-trade join (396 shared): A−B $12.86/tr (50 WIN→LOSS flips), A−C $46.32/tr —
the artifact exceeds the recorded expectancy. A −8% stop on 0DTE OTM-1 sits inside 5-min bar
noise (385/399 stop-touched), so the fill convention IS the result. Note the gap-through-open
optimism (the C leg) is a *disclosed* convention shared by the sim AND the t4/t5/P5 replay
harness ("touch stops", "frictionless") — disclosed does not mean immaterial at tight-stop/OTM
scale; live stops are market orders and fill at-or-worse than the touch level.

**Fix (proposed, NOT shipped — re-baselines historical studies, needs the conscious-convergence
protocol from the 2026-07-09 lesson):** (1) simulator_real (+ _trailing copy): a ratchet computed
from bar N binds from bar N+1 — snapshot `effective_stop` at bar start for all stop checks/fills;
add gap-fill `min(stop, bar.open)`; ship together with a re-scored funnel so old/new numbers are
never mixed (test_profit_lock_scope_pin.py will RED by design — update it in the same commit).
(2) t4_exit_matrix/t5 replay: `stage=="premium_stop"` should fill at
`dec.state.runner_stop_premium` (byte-identical for post_tp1 pre-TP1 exits, correct for "full") —
blocked tonight only because t4 carries another session's uncommitted edits. (3) Any tight-stop
(<~15%) OTM cell ratified on touch-fill conventions owes a gap-fill sensitivity pass before
arming anything.

**Generalization:** OHLC bars carry no intra-bar sequence — any replay rule that lets the same
bar's favorable extreme rescue its adverse extreme (ratchet-then-check, target-before-stop) is
heads-you-win accounting, and it compounds silently with touch-fill optimism. Check every exit
against state as of bar-OPEN; anything learned from bar N acts on bar N+1; when a bar opens
through a stop, fill at the open. And when two engines disagree, suspect BOTH before crowning
either: here the "live-parity" replay was wrong pessimistically (fill map) while the sim was
wrong optimistically (look-ahead) — the truth (−$11/tr) sat outside the bracket the two numbers
drew. Playbook §2.12 has the transferable write-up.

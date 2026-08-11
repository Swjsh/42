# Exit-path failure modes — "if we're in a trade and the stop is breached, what stops us getting out?"

**2026-08-10 night audit.** J: *"if we get into a trade, if we get into a stop loss, are we
gonna be able to get out if x, y, and z happens? This needs to be bulletproof."*

Method: walk the exit path adversarially instead of waiting for a test to fail, then drive the
REAL `exit_actuator.manage_tick` against brokers engineered to misbehave — one failure mode per
scenario. Reproduce with:

```bash
python backtest/tools/exit_chaos_drill.py
```

Every scenario: 3 lots, entry 1.16, quote collapsed to 0.45 (61% down, far through the −50%
catastrophe cap). A correct engine sells on the first tick it can.

---

## Chaos-drill results

| scenario | sells | verdict |
|---|--:|---|
| healthy baseline | 1 | **ESCAPED** |
| quote feed dead 3 ticks, then recovers | 1 | **ESCAPED** — transient outages are survivable |
| sell REJECTED once, then healthy | 1 | **ESCAPED** — retries on the next tick |
| partial fill (2 of 3) | 1 | **ESCAPED**, remainder handled (see gap 4) |
| a sell is already RESTING | 0 | BY-DESIGN — no duplicate stacked |
| WATCH mode (arm not live) | 0 | BY-DESIGN — places nothing |
| **option quote feed DEAD (persistent)** | 0 | 🚨 **TRAPPED** |
| **sell rejected EVERY tick** | 0 | 🚨 **TRAPPED** (broker-side; nothing we can do but alarm) |
| **position query ERRORS persistently** | 0 | 🚨 **TRAPPED** (correct fail-closed, but no exit) |

Every TRAPPED row has exactly one backstop: the **15:55 EOD flatten**
(`fleet_eod.close_all_spy_options`), which is a separate scheduled task and reads no exit
state — good isolation, but it means the whole day's tail risk rests on one task firing.

---

## FIXED tonight (committed, guard-tested, RED-proofed)

**1. Kill switch froze the stop-loss — fleet-only, most serious.**
The exit pass was gated on `... and not breaker.tripped`, so a tripped arm fell to WATCH: it
planned the stop and placed nothing. Measured: the same position placed 1 sell with the breaker
OK and **ZERO** with it tripped. The stop switched itself off at exactly the moment the account
was losing most. Rule 5 governs ENTRIES; exiting is risk reduction. `heartbeat_core` was always
correct (`live=ARMED`, no breaker term) — this was fleet diverging. Entries stay blocked by two
independent gates, both pinned by tests.

**2. No orphan-position safety net on fleet arms.**
`_adopt_untracked_positions` existed only in `heartbeat_core`, so safe-3 / risky-1 / risky-3 had
none. `load_states` fails open to `{}` on unreadable JSON and `manage_tick` returns `[]` on empty
state → any loss of exit-state left a live position with ZERO management until 15:55. That is the
shape of today's risky-1 −$440. The pending-fill guard closed the *cause* seen that day;
`adopt_untracked_positions` closes the *class*. Engine-placed orphans (proven from the arm's own
ledger) get the full ladder back anchored to the broker's avg entry; unknown provenance stays
cap-only; unreadable provenance fails **closed** to cap-only.

**3. Re-anchor could silently lower an armed ladder floor.**
`reanchor_entry` refuses on `tp1_filled or profit_lock_armed` — and the pre-TP1 ladder
deliberately sets neither. RED-proof: floor drops **1.8560 → 0.8800**, turning a locked +60% into
a −50% cap ride. Not reachable today (both call sites re-anchor same-tick), but that was a timing
argument; the guard is now structural.

---

## OPEN — daylight decisions, deliberately not changed unsupervised

**4. A partially-filled SELL_ALL prunes the exit state with lots still open.**
`if dec.closes_position and (not live or sell_placed_ok): del states[symbol]` treats *accepted*
as *filled in full*. Drill: sells=1, leftover qty=1, tracked=False.
*Residual risk is bounded to ONE tick* — adoption re-registers the remainder next tick (fleet via
`manage_tick(adopt_untracked=True)`, core via its own adopt), verified in the drill.
*Why not fixed tonight:* the principled fix (only the position read may prune) changes prune
timing for every position on BOTH engines, and four existing tests encode the current contract —
a blast-radius walk, not a 2am edit to shared exit semantics.

**5. A persistently dead option-quote feed silently disables the stop.**
`get_option_quote_hilo → None` logs `action: HOLD, reason: no_quote` and nothing alarms on it, so
a position can sit all day with no stop enforcement and no signal. Transient outages are fine
(proven). Needed: a consecutive-`no_quote` counter that escalates loudly after N ticks.

**6. A persistently rejected sell is invisible.**
`sell_placed_ok=False` correctly prevents pruning and correctly retries, but nothing escalates.
An arm that cannot sell all day should be screaming, not retrying quietly.

**7. The 15:55 EOD flatten is a single point of failure** for every TRAPPED mode above. It has no
redundancy and its own failure would be silent. Worth a second, independent verify-flat pass.

---

## Not defects (verified good)

- Sell retry after a rejection works.
- The duplicate-sell guard prevents stacking when an order is already resting.
- A position-query error fails **closed** (holds state, never prunes) — correct.
- The EOD flatten reads no exit state, so state corruption cannot disable it.
- `runner_stop` breach sells the **full** position pre-TP1 (matches the replay model).

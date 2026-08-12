---
filed: 2026-08-12
filed_by: goal fire (unlock-more-trades, ~01:30 ET)
kind: lesson
status: pending
---

# A CONTROL test has been failing since 2026-08-03 — which means the C31 never-average-down guard's refusal assertions may have been passing VACUOUSLY for 9 days

## Symptom

Full suite (first complete run in a while): **77 failed, 8383 passed, 9 skipped, 7 xfailed**
in 62 min. Four failures share one message:

```
SKIP_ORDER_QUERY_ERROR: could not confirm no pending BUY order for SPY...
```

in `test_never_average_down_2026_07_20.py` (1) and `test_min_entry_premium_floor.py` (3).

## Root cause

`heartbeat_core._execute` gained an **order-level idempotency guard** on 2026-08-03
(`b80b799c`), LAYER 2 of which calls `fb.open_buy_orders_checked(creds, symbol)` and **fails
CLOSED** on a query error — correct production behaviour (a missed entry is cheap, a double
entry is not). The affected test harnesses never stubbed that primitive, so in-test the query
errors, the guard refuses, and every `_execute` call returns `SKIP_ORDER_QUERY_ERROR` instead
of reaching placement. **Not a production defect — a test-harness gap opened by a production
ship that did not walk its own blast radius.**

## Why this is worse than "4 red tests"

The failing case in `test_never_average_down_2026_07_20.py` is
`test_control_when_flat_the_route_still_works`, and its own docstring states its purpose:

> "Sanity control: the harness itself is capable of a PLACED result when `account_flat=True`,
> proving the NOT_FLAT result above is the flat-check firing, not a harness artifact swallowing
> every attempt."

The control exists precisely to rule out "everything gets refused for an unrelated reason."
**That is now exactly what is happening.** Its sibling assertions (`NOT_FLAT` refusal, C31
never-average-down, guard-pinned per CLAUDE.md OP-25 C31) still report PASS — but with the
control dead they can pass **vacuously**: everything is refused, including the case that is
supposed to succeed. The author built the exact tripwire for this failure mode, and the
tripwire has been red for 9 days without anyone reading it.

C31 is load-bearing doctrine (J's 667 real trades: 3+ lots −$17,461; the no-add + catastrophe-cap
package is the recoverable-money finding). Its guard being unverified for 9 days is the finding,
not the red count.

## Rule to carry forward

1. **A red CONTROL test invalidates its siblings' green.** Triage controls FIRST, not last — a
   suite summary that says "1 failed, 5 passed" in a class with a dead control is really
   "6 unverified."
2. **Shipping a fail-CLOSED production gate requires walking every test that drives that code
   path.** A gate that refuses on unstubbed I/O will silently convert existing tests into
   vacuous passes rather than loud failures.
3. **Never let a full-suite run stay unrun.** These sat 9 days because the suite takes 62 min
   and nobody ran it to completion; two prior attempts in one session died on timeouts and were
   nearly reported as "green".

## Work order (scoped, test-only — no production change)

Stub `fleet_broker.open_buy_orders_checked` -> `([], True)` in the harnesses of
`test_never_average_down_2026_07_20.py`, `test_min_entry_premium_floor.py`, and any sibling
driving `heartbeat_core._execute`; then RE-RUN and confirm the control reaches `PLACED` and the
NOT_FLAT refusals still refuse **for the flat-check reason**, not the query-error reason.
Assert on `plan["status"]` values specifically, so a future refusal-for-the-wrong-reason fails
loud instead of passing.

Also triage the remaining ~73 failures by cluster (top files: `test_unattended_health` 5,
`test_setup_dispatch` 5, `test_trigger_level_exact_provenance` 4) and record which are
environment/state-dependent vs real regressions.

Kin: C7 (silent success is failure — audit outputs, not exit codes), C14 (vary-and-assert).

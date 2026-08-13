---
filed: 2026-08-12
filed_by: opus (conviction build, J correction)
kind: lesson
status: pending
---

# Twice in two days: declared data "unavailable" from ONE blocked path, when a second path was open the whole time

## Symptom — two instances, 24 hours apart

1. **OPRA (2026-08-11/12).** Recorded blocker: `/v1beta1/options/bars` returns 403 "OPRA
   agreement is not signed", therefore "we cannot price the hold-vs-dump counterfactual" and
   a $900 question was declared unanswerable. **Reality:** bars return 200 on the FREE tier and
   reject a `feed` param outright; the 403 came from a *different* endpoint
   (`quotes/latest?feed=opra`) that no repo script calls. The data was free and always available.
2. **Conviction backtest (2026-08-12).** Declared "NOT BACKTESTABLE — the score's four best
   inputs were never persisted", because historical ledgers store only flattened level floats.
   **Reality:** `refresh_levels_intraday.refresh(df=None)` takes an injectable DataFrame — its
   own comment says *"df injectable for tests/replay (G6 seam pattern)"* and an existing test
   already uses it. The level records REGENERATE from bars. J caught this one:
   *"we could definitely just replay the days."*

## Root cause

Both times the reasoning was **"the OUTPUT isn't there, therefore the DATA isn't obtainable."**
That step is invalid whenever a PRODUCER exists that can be re-run. In a repo where most state
files are generated on a schedule by a script that accepts its inputs as arguments, it is
almost always invalid.

Aggravating factor: an authoritative-sounding artifact of the failure (a 403 body; an empty
column in a ledger) reads as proof, so the search stops. The second path is never probed.

## Rule to carry forward

1. **Before declaring data unavailable, ask: is there a PRODUCER, and can it be re-run?**
   Grep for the script that writes the file and check whether its inputs are injectable.
   "Not stored" != "not obtainable".
2. **One blocked endpoint/path is not a capability verdict.** Enumerate the endpoint FAMILY (or
   the call sites of the producer) and probe each before concluding. Both incidents were a
   single probe generalised into a blanket "we don't have this".
3. **A blocker recorded in a doc inherits authority it never earned.** Both "blockers" were
   written into planning docs and then cited by later work as settled fact. When recording a
   blocker, record the exact probe that produced it so the next reader can re-run it in one
   command — an unreproducible blocker should be treated as unverified.

Kin: C7 (silent success/failure), C14 (dead knobs — vary-and-assert), and the
CAPABILITY-AUDIT-2026-08-12 lesson (conformance audits cannot see missing capabilities).
Sibling instances are cheap to find and expensive to miss: each of these cost roughly a day.

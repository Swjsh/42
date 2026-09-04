# Lesson inbox -- unit tests stub the exact lookups that fail closed; rehearse the whole path in shadow on a REAL account before an armed lane's first session

**Filed:** 2026-09-04 ~02:00 ET (Fable, tickers-lane build)  **Theme:** C7 silent success / C11 broker is truth / C14 dead-or-unapplied knobs
**Severity:** two day-one blockers + one blocker-class exit bug, all invisible to a 54-test green suite

## Symptom
`multi/execute.py` (three new non-SPY 0DTE paper arms, first session 2026-09-04 09:35 ET) had 54 green tests, both AST
no-order guards green, and a live read-only scorer smoke. A shadow end-to-end probe -- the real executor, launched
exactly as the scheduled task launches it, against a real paper account, with `armed=False` and all state redirected
to scratch -- found in three runs what the suite could not:
1. `risk.py::sector_for_symbol` FAILS CLOSED on a symbol missing from `params.universe`; the universe had been emptied
   to keep a 72-name list out of scoring. Every entry on every arm would have been BLOCKED at the open.
2. A 2% per-trade cap on the probe account could not afford the Rule-6 minimum of 3 contracts -- SIZE_BELOW_MIN forever.
3. (adversarial review, same night) `core.manage_open_positions` passed `open_qty=record.qty` -- the ORIGINAL entry
   qty, documented as never-decremented -- so after a TP1 partial every SELL_ALL would request 3 against 2 held.
   `test_multi_exits.py:289` already showed the intended caller contract; no caller honoured it. C11 re-violated.

## Root cause, one sentence
The unit tests stub `risk.evaluate_admission`, `size_entry` and the broker positions read -- the exact three lookups
that fail closed in production -- so a green suite proved the glue, not the path.

## Fix shipped
`--e2e-probe-root` mode on the executor (shadow-only, borrows an existing paper key, ignores the session window,
redirects every path to scratch) and the rule below. Broker-truth `open_qty` + `STALE_STATE` rows pinned by
`backtest/tests/test_tickers_exit_qty_2026_09_04.py`.

## Proposed rule (for the L## entry)
Before an armed lane's FIRST session, run its real executor in shadow against a real account through every gate to
the order-preview line, and read the BLOCKED reasons -- a green unit suite is necessary, never sufficient. Graduate:
any lookup that fails closed on missing config gets a probe assertion, not a mock.

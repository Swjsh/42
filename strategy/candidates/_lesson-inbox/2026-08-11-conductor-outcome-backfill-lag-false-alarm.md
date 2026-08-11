## Lesson candidate: a per-fire metric snapshot taken before a separate backfill job runs reads as a false regression/break

**Date:** 2026-08-11
**Class:** C7 (silent success is failure — audit outputs) / adjacent to L293 (a monitor's numbers need a provenance stamp or downstream consumers inherit unsound soundness sight-unseen)

**What happened:** `conductor_outcome.py`'s `trading_function_snapshot()` reads
`journal/trades.csv` to count same-day fills. `fleet_journal_bridge.py`
backfills that CSV from broker-truth (`pnl-statement.json`) on its OWN
schedule, well after a trading day ends. Three conductor fires on the night
of 2026-08-10/11 (22:40, 00:50, 01:55 ET) all called `record()` BEFORE that
backfill had landed for 2026-08-10, so all three honestly snapshotted
`fills: 0` for a trading day that actually had 6 real broker fills
(`fill_funnel.py --date 2026-08-10` = GREEN). `conductor_outcome.py metric`
then reported `fills: 0` / `trend: "regressing"` to the NEXT fire, which read
as "the trading function may be broken" — a queue item
(`VERIFY-2026-08-10-ZERO-FILLS-DESPITE-ACCEPTED-ORDERS`) was filed HIGH
priority specifically to chase this down, and this fire spent real budget
re-verifying something that was never actually broken.

**Root cause (one sentence):** two independent producers (the live trading
ledgers and the backfill-from-broker-truth job) write to the same read
surface on different schedules, and the metric consumer took a single
point-in-time read as ground truth instead of accounting for the fact that
its own dependency is eventually-consistent, not immediately-consistent.

**Fix shipped:** `compute_metric()` now reconciles the function fields
(`fills`/`orders_accepted`/`enters_last_trading_day`/`distinct_setups_traded`/
`extra_exec_orders_accepted`) per `trading_day` to the MAX seen across the
full outcome history before computing `function_latest`/`trend`/
`function_score_avg`. This is safe specifically because these fields are
monotonically non-decreasing as a completed day's ledgers get backfilled —
nothing "un-fills". The on-disk append-only ledger (`conductor-outcomes.jsonl`)
is never rewritten; this is a read-layer correction only in
`setup/scripts/conductor_outcome.py`. 5 new guard tests
(`backtest/tests/test_conductor_outcome_backfill_reconciliation.py`),
RED-proofed via `git stash` (1/5 correctly failed pre-fix on the exact
reconciliation assertion, 4/5 passed by construction on unrelated axes).
2 pre-existing tests in `test_conductor_outcome_function.py` had to be
corrected (not weakened) — they used the SAME literal `trading_day` string
for both "older" and "recent" halves of a trend comparison as a convenience
shorthand, which the new reconciliation (correctly) treats as one real day
and blends. Fixed by giving each half a distinct, realistic trading_day —
same assertions, same intent, now representative of how sequential fires
actually snapshot sequential distinct calendar days.

**General pattern for the lesson index:** when a consumer reads a value from
a data source that is written by MULTIPLE producers on DIFFERENT schedules
(a live-tick writer + a separate backfill/reconciliation job), a single
point-in-time read cannot be trusted as "final" until the read layer either
(a) knows the backfill job's cadence and waits for it, or (b) reconciles
across all available reads for the same logical key to the best-known value
(this fix's approach — safe when the field is provably monotonic). Otherwise
every consumer downstream of that read inherits a race condition that reads
as a real signal (here: a false "trading function broken" alarm) instead of
a timing artifact.

**Suggested L# graduation:** fold into the C7/L293 cluster as an explicit
example of "monitor's own read timing vs a separate backfill job's timing"
— the sibling of L293's "coverage scope rot" but for temporal staleness
instead of scope staleness.

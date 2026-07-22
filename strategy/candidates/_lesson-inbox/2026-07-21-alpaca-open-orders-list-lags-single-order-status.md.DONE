candidate lesson (fold under C11 -- broker is source of truth: verify flat before entry)

**Filed:** 2026-07-21 ~21:15 ET, conductor (AFTERHOURS)
**Symptom:** `Gamma_DressRehearsal`'s nightly artifact showed `check1_options_safe: RED` with
evidence "NOT CLEAN: open_orders=1" -- even though the SAME run's post-cancel poll on that
exact order id (`GET /v2/orders/{id}`) had already returned `status='canceled'` moments
earlier. `check1_options_bold` (byte-identical code path, same script, same run) came back
GREEN with `open_orders=0`. `self_check.py` escalated this to verdict=BROKEN ("Tomorrow's
open is NOT proven").

**Root cause:** Alpaca's `GET /v2/orders?status=open&limit=100` LIST endpoint is backed by a
different index/cache than the single-order `GET /v2/orders/{id}` lookup. Immediately after a
cancel is confirmed via the single-order endpoint, the list endpoint can still show the order
for roughly 1-2 seconds (eventual consistency between the two read paths) before it catches
up. This is a variant of C11's "broker is source of truth, verify before acting" theme, but
the twist is new: **two different broker READ endpoints for the same underlying state can
disagree with each other for a short window, not just "broker state vs local cache."** Any
code that polls endpoint A to a terminal/confirmed state and then immediately queries
DIFFERENT endpoint B expecting that same state to be reflected is exposed to this class.

**Fix shipped:** `setup/scripts/dress_rehearsal.py` `check1_options_acceptance`'s end-state
check now retries the open-orders/positions listing up to `END_STATE_RETRIES=5` times,
`END_STATE_RETRY_SLEEP=1.5`s apart, before declaring NOT CLEAN -- mirrors the file's own
pre-existing `_flatten_crypto` verify-flat retry shape. Guards:
`backtest/tests/test_dress_rehearsal.py::TestEndStateRetryTolerance` (3 tests: transient
staleness clears on retry, genuine residue still REDs -- never silently softened, clean case
costs only 1 try). Verified live against the real Alpaca paper API this fire: RED -> GREEN.
Commit `d6cc86a`.

**Generalization for lesson-author to consider:** any OTHER place in the codebase that polls
a single-resource broker endpoint to a terminal state and then immediately trusts a SEPARATE
list/bulk endpoint to already reflect it (fleet exit management, `fleet_broker.open_sell_orders`,
`_flatten_crypto`'s own position-read step, EOD-flatten's "verify flat" checks) is a candidate
for the SAME class of transient false-RED/false-not-flat. Worth a grep audit for
`orders?status=open` / `get_positions` calls that immediately follow a single-order terminal-
status confirmation, to see if any of them need the same retry tolerance (or already have it
via a different mechanism -- `_flatten_crypto` already retries, so it's likely already immune;
this is about finding OTHER instances, not re-fixing this one).

**First occurrence** -- not yet graduated to a broader code assertion beyond this one fix;
watching for a repeat per OP-25 before treating it as a systemic pattern needing a shared
helper (e.g. a `verify_broker_listing_settles(...)` utility other scripts could reuse).

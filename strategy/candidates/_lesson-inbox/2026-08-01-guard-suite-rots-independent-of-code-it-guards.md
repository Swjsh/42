## A green-at-ship guard suite can silently rot into RED with zero code regression — two mechanisms found in one file

**Found:** 2026-08-01 conductor-weekend fire, while closing the stale `PMH-IS-FABRICATED-IEX-PREMARKET`
queue checkbox (see the paired update to `2026-07-23-stale-queue-checkbox-work-done-ticket-open.md`
in this inbox — that ticket's underlying fix (commit `7b4aa3f4`, 2026-07-27) had already shipped and
was correct; investigating "is this really still open?" surfaced that its OWN guard suite
(`test_level_compiler_v2_guards.py` + `test_refresh_levels_intraday.py`) had gone RED on
2026-07-28 — the very next day — with ZERO change to the production code it guards. Fixed +
RED-proofed, commit `155ab21e`.

**Two distinct mechanisms, same symptom class (a "regression" that isn't one):**

1. **Hardcoded past date in a fixture, compared against real wall-clock time.**
   `test_read_levels_byte_identical_old_vs_new_schema` +
   `test_read_levels_bite_a_real_price_change_is_NOT_byte_identical` built fixture levels with
   `expires_at="2026-07-27T16:00:00-04:00"` (the day the test was authored). The production code
   under test, `heartbeat_core._level_expired()`, compares `expires_at`'s date against
   `_et_now()` — the REAL current ET date, unmocked in the test. The instant wall-clock crossed
   2026-07-27, every fixture level "expired," `_read_levels()` returned `([], [])` for both
   old-style and new-style input, and the "byte-identical" assertion passed **vacuously** (empty
   == empty) while the test's own explicit non-vacuous bite check (`assert old_out[0] != []`)
   correctly caught the vacuity and failed. **The bite assertion is why this was even
   detectable** — without it, the byte-identical test would have silently passed forever on two
   empty lists, proving nothing, and nobody would ever have known.
   **Fix pattern:** any fixture date compared against real current time must either (a) be a
   far-future constant (what was shipped: `2099-12-31`) so it structurally cannot rot, or
   (b) monkeypatch the code's own `_et_now()`/`et_now()` seam to a frozen date, never a bare
   same-day string. Same-day-authored past dates are a ticking bomb with a ~24h fuse.

2. **A "unit" test silently depends on real, live, unmocked external state.**
   `test_refresh_flag_on_injects_memory` builds a fully synthetic OHLCV `df` and asserts a
   specific `INTRADAY_PMH` label appears in the output — but `refresh()` ALSO unconditionally
   unions real multi-week shelf zones from `daily_context.py` (a module-level global, disabled
   only when explicitly `None`), which reads the REAL, current SPY price-history cache. On
   2026-08-01 the synthetic PMH (749.5) happened to fall inside an ACTUAL live shelf zone
   (748.66–750.26); the dedup collapse rule (levels within `ROLE_EPSILON=0.10` of each other
   merge into ONE, higher-weight source wins) let the real shelf (weight 5) silently absorb the
   synthetic intraday level (weight 2), and the label the test was asserting on never made it
   into the output. **The test's pass/fail was a function of TODAY'S real market structure, not
   of the code being tested** — it would flip unpredictably day to day as real shelf zones move,
   independent of any actual bug.
   **Fix pattern:** any test exercising a function with an unconditional "union in real
   external/live state" side-channel must monkeypatch that channel to a disabled/mocked state
   UNLESS the test is specifically exercising that channel. Here the fix was
   `monkeypatch.setattr(rli, "daily_context", None)` — already a first-class supported code path
   (`if daily_context is not None:`), so no new seam had to be built, just wired into the shared
   `_state` fixture so every consumer gets isolation for free.

**Why this matters beyond these two tests:** a guard suite exists to make "did I break this?"
answerable by machine instead of memory (OP-25's entire thesis). A guard that can independently
rot — via calendar drift or via live-data leakage — inverts that contract: it either cries wolf
(burning a future fire's time re-diagnosing a non-bug, as this ticket nearly did) or, worse,
goes quietly green on a vacuous comparison and stops guarding anything at all (mechanism #1,
had the bite assertion not existed). **Recommend auditing other `_read_levels`/`refresh_levels`-
adjacent test fixtures for the same two patterns** (grep for `expires_at.*-04:00` with a literal
past-looking date, and grep for tests that call `refresh()`/`compute_daily_context()` without an
isolation monkeypatch) — not done this fire (rail 3, one bounded task), flagging as a
follow-up scope, not a new incident.

**Recommended graduation (don't just re-note in prose):** consider a lightweight repo-wide CI/
pytest-collection-time lint that flags any string literal matching `\d{4}-\d{2}-\d{2}T` inside a
test file where the year is more than ~60 days in the past relative to the CURRENT date at lint
time (a "this fixture date is stale or about to be" nudge) — same spirit as the stale-queue-
checkbox cross-reference check recommended in the paired lesson item, applied to test fixtures
instead of queue.md. Not actioned as code this fire; filed for `lesson-author` to encode as an
`L##` and fold into **C6** (no-look-ahead / temporal-scope class) alongside a note that this is
the FORWARD-time mirror of C6's usual backward-look-ahead shape, plus **C7** (silent-success-is-
failure) for mechanism #1's vacuous-pass sub-case.

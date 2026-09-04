# Lesson inbox — bare-value-into-dict-contract crash, invisible to single-tick fuzzing

**Routed by:** Gamma_Conductor (T7 tickers-lane day-one autopsy) 2026-09-04
**Priority:** MED
**Category:** producer/consumer contract mismatch + test-methodology blind spot

## The finding

`multi/lib/context.py::update_level_states` built `LevelStateRec.bounce_history` as a list of
BARE FLOATS. Every consumer that reads it — `multi/lib/filters.py::detect_sequence_rejection`/
`_reclaim` (the fork) AND `backtest/lib/filters.py::detect_sequence_rejection`/`_reclaim`
(production, FROZEN) — subscripts each entry (`e["high_reached"]`/`e["low_reached"]`),
matching the reference shape `backtest/lib/orchestrator.py::update_level_state` has always
produced: `{"bar_idx": ..., "high_reached"|"low_reached": ...}`. A bare float raised
`TypeError: 'float' object is not subscriptable` — 144 times across 3 paper accounts on the
tickers-lane's first live trading day, each occurrence aborting that tick's ENTIRE remaining
symbol-scoring loop (the exception escaped the narrow `except (SignalBuildError, ValueError)`
around the scorer call, all the way to the per-arm outer handler).

**Why it survived 54+ unit tests and a 313K-token adversarial review pass**, and why a prior
session's own targeted fuzz effort ("1500+ synthetic bar/level combinations") never reproduced
it: the crash only fires once a level has accumulated **3+ bounce touches while holding a
`broken_to_resistance`/`broken_to_support` role** — a condition that requires STATE
PERSISTENCE ACROSS MULTIPLE TICKS (the function reads/writes a per-symbol JSON file across
calls). A single-shot fuzz harness that calls the function once per synthetic bar/level
combination can never build that accumulated history, no matter how many combinations it
tries — the bug lives in the SEQUENCE of calls, not in any one call's inputs.

## Generalizable lesson

For any function whose behavior depends on **state accumulated across repeated calls**
(a per-symbol/per-level memory file, a rolling window, a ratchet), a fuzz/property test that
calls it once per synthetic input is structurally blind to bugs that only manifest after N
calls. The reproduction that actually worked here was a **multi-call simulation** — build a
short sequence of ticks that drives the state machine through the specific transition
(role flip -> 3 distinct bounce touches) the bug lives in, using the SAME state-persistence
path (a tmp_path-scoped `state_dir`) production actually exercises.

**Actionable guard pattern (recommend for `validator-author`):** any stateful-across-ticks
producer (level memory, ratchet, cooldown, breaker) should get at least one test that drives
it through >=3-5 sequential calls with real state persistence, not just single-call property
tests — the class of bug this misses is exactly "the Nth call breaks given what the first
N-1 built," which single-call fuzzing cannot see by construction.

## Fix shipped this fire

`multi/lib/context.py::update_level_states` now appends
`{"bar_idx": <int>, "high_reached"|"low_reached": <price>}` — the two keys both frozen
consumers actually read, nothing invented (no fabricated `outcome` field). Guard:
`backtest/tests/test_level_state_bounce_history_shape_2026_09_04.py` (3 tests, RED-proofed
via `git stash`/`pop`: fails on pre-fix code with the identical live `TypeError`, including a
dedicated test that feeds the OLD bare-float shape into both frozen detectors and asserts they
raise). Full suite `pytest backtest/tests/ -k "multi or tickers or level_state" -q` — 551
passed. Not on `FROZEN_TRADING_PATH`.

## Priority / dependencies

depends:none :: status:pending

---
title: log.error()/logging calls with no attached Handler are a black hole under a headless (pythonw, no console) deployment
date: 2026-08-30
source: conductor-weekend fire, FUTURES-HEALTH RED triage
class: C7 (silent success is failure — audit outputs, not exit codes) — new specific sub-pattern
---

## Symptom

`Gamma_FuturesBrokerLane` (real-fill parity lane on Tastytrade sandbox,
`backtest/futures/tastytrade_paper.py`) went from a ~5% baseline connect-failure rate to
76% over 2026-08-24 → 2026-08-28 (`automation/state/futures/trader-broker/decisions.jsonl`).
`self_check.py` flagged `FUTURES-HEALTH RED` — "signals seen but entry refused repeatedly" —
but there was **zero recoverable reason anywhere on disk**: `broker-transport.jsonl` had
never been created despite the diagnosability mechanism (`_log_broker_transport`) existing
since 2026-08-29, and the ledger row only ever carried the generic
`reason="broker_not_connected"` with a static human-authored `detail` string, never the
actual exception.

## Root cause

`TastytradeBroker.connect()`'s `except` blocks called `log.error(...)` and nothing else:

```python
except Exception as e:
    log.error("Tastytrade connect failed: %s: %s", type(e).__name__, e)
    ...
    return False
```

Python's `logging` module writes to whatever `Handler`s are attached to the logger (or its
ancestors) — with **zero handlers attached**, `log.error()` is a complete no-op (the
`lastResort` handler only fires at WARNING+ *and* only if `sys.stderr` exists and is
writable; under `pythonw.exe` there is no console and no `sys.stderr` at all). Neither
`futures_trader_runner.py` nor `tastytrade_paper.py` nor anything upstream ever calls
`logging.basicConfig()` or attaches a `FileHandler`. So the ONE place the real exception
class/message existed was inside a function call that provably went nowhere — every single
failed tick discarded its own root cause on purpose-shaped code that looked like it was
logging the failure.

This is NOT the same lesson as the existing pythonw window-leak lessons (L20/27/33/41/81/
210/229/277/297, C8) — those are about a visible window/process leaking. This is about a
**Python-level `logging` call silently vanishing** even when the process itself runs
perfectly cleanly, exits 0, and writes all its OTHER intended state files correctly. The
process looked completely healthy from the outside; only the ONE piece of information
needed to diagnose the next failure was gone.

## The generalizable rule

**Never rely on `logging.error()`/`log.warning()` etc. as the ONLY record of a failure
reason in any script that may run under pythonw, a scheduled task, or any other
console-less/detached deployment.** Any exception detail that a future investigation will
need MUST also land in a durable, structured sink the script already writes reliably:
a state-attribute the caller reads (`self.last_failure_detail`, mirroring how
`place_bracket_entry` already did this), and/or an appended JSONL row, and/or a field on
the per-tick ledger record that already gets written unconditionally. `logging` calls are
fine as a supplementary trail for the rare case a handler IS attached (e.g. interactive
`python -c` runs, which is how this was reproduced live) — they must never be the SOLE
trail for anything a headless production task depends on.

## Fix shipped this fire

`backtest/futures/tastytrade_paper.py::TastytradeBroker.connect()` now sets
`self.last_failure_detail` in both except branches (missing-env-var AND generic exception)
and unconditionally appends a row to `broker-transport.jsonl` via the existing
`_log_broker_transport` helper — for both the transport-error case (already covered) and
the previously-uncovered non-transport auth/config case. `futures_trader_core.run_tick()`
carries `broker.last_failure_detail` through into the `connect_failure` field of the
not-connected ledger row. Guard: `backtest/tests/test_futures_broker_connect_diagnosability_2026_08_30.py`
(7 tests, RED-proofed against the pre-fix code via `git stash`).

## Suggested guard for `lesson-author` to consider generalizing

A repo-wide grep for `log\.(error|warning|critical)\(` in any module reachable from a
pythonw/`run_cmd_hidden`/`run_exe_hidden` launch path, cross-checked against whether that
same except-block also writes to a structured sink. Out of scope for this fire — flagging
for the author to size.

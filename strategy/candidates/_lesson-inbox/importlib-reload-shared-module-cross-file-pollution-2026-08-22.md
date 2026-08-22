# Lesson candidate: `importlib.reload()` on a shared production module corrupts OTHER test files' class references

**Date:** 2026-08-22 (conductor AFTERHOURS)
**Class:** C7 (silent success is failure — audit outputs, not exit codes) + a new isolation-discipline theme

## Symptom

Full-suite `pytest backtest/tests/ -q -m "not slow"` failed 9 tests identically across at
least 3 conductor fires on 2026-08-21 (23:15 / 23:34 / 23:59 ET), always the same node IDs.
5 of the 9 were in `test_setup_dispatch.py` (`TestFlagOnMockedDetector` + `TestDetectorError`).
Every one of those 5 **passed when run standalone or in a small multi-file subset** — the
textbook "polluted only in the full suite" shape, which is exactly why 3 separate fires
re-triaged it as "TEST POLLUTION (5+2), a different defect class" without finding the
mechanism.

## Root cause

`backtest/tests/test_gap_prior_close.py` did:

```python
import setup_dispatch as sd
importlib.reload(sd)
```

`importlib.reload()` re-executes the module's code **in the same module object**, which
means every `class Foo:` statement inside re-runs and rebinds the module attribute to a
**brand-new class object**. `sys.modules["setup_dispatch"]` keeps its identity, but
`setup_dispatch.SetupDispatcher` and `setup_dispatch.DispatchResult` become NEW classes
after the reload.

`test_setup_dispatch.py` does `from setup_dispatch import SetupDispatcher` at **collection
time** (pytest imports every test module up front, before any test runs), capturing the
OLD class object into its own module namespace. When `test_gap_prior_close.py`'s test
later **executes** (alphabetically before `test_setup_dispatch.py` — "g" < "s" — so it runs
first) and reloads the module, `setup_dispatch.SetupDispatcher` in `sys.modules` becomes a
NEW class. `patch("setup_dispatch.SetupDispatcher.<method>", ...)` is a STRING lookup that
resolves the module attribute at patch time — i.e. the NEW class — but
`test_setup_dispatch.py`'s tests instantiate the OLD class (via their own already-bound
`SetupDispatcher` name). The mock patches a class nobody instantiates; the real method runs
instead; `mock_method.assert_called_once()` fails with "Called 0 times", or the real
(unmocked) detector logic produces a different `skip_reason` than the test expected.

## Why this stayed hidden for so long

- Collection-time imports (`from X import Y`) happen once, up front, for the WHOLE suite —
  invisible in any single-file or `-k`-selected sub-run unless the polluting test's
  **execution** (not just its module's import) precedes the affected test's execution.
- `-k`-based deselection still collects (imports) every module but SKIPS running deselected
  tests — so a `-k "test_a or test_b"` repro will NOT reproduce reload-based pollution, only
  import-time pollution. This cost real time before the mechanism was found (a `-k` probe of
  just the 2 vwap/gap tests against the full 10,057-test collection PASSED, initially looking
  like it ruled out cross-file interaction entirely).
- The fix (`monkeypatch.setattr(sd, "_REPO", tmp_path)`) already existed in the same test and
  was sufficient on its own — the `reload()` call served no purpose that monkeypatch didn't
  already cover; it was dead defensive code that actively broke something else.

## Fix shipped

Removed the `importlib.reload(sd)` call from `test_gap_prior_close.py` (2026-08-22,
conductor AFTERHOURS). Added `backtest/tests/test_no_setup_dispatch_reload_pollution_2026_08_22.py`:
a comment-aware source-sweep guard that fails if ANY test file `importlib.reload()`s a name
bound to `setup_dispatch`. RED-proofed by temporarily restoring the original buggy line
(reproduced the exact 3-of-5 setup_dispatch failures + both new guard-test failures), then
confirmed green after restoring the fix.

## Generalizable guidance (for `lesson-author` to fold into LESSONS-LEARNED.md)

**Never `importlib.reload()` a shared production module from a test** unless the module is
owned exclusively by that one test file (no other test file does
`from that_module import SomeClass` at its own top level). If you need a "clean slate,"
`monkeypatch.setattr` the SPECIFIC attribute you need reset — it auto-restores and never
touches the shared class objects other tests' collection-time imports already captured. If a
genuine fresh-module-execution semantic is required (e.g. simulating "a new scheduler
process started"), load an ISOLATED copy via `importlib.util.spec_from_file_location` +
`exec_module()` into a local variable — never reassign into the shared `sys.modules` slot.

Suggested lesson number: next available (check current max in LESSONS-LEARNED.md).

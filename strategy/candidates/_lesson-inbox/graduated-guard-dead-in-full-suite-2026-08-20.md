# A graduated guard has been DEAD in every full-suite run — killed by test pollution

**Date:** 2026-08-20 (found incidentally while regression-checking the multi-symbol lane)
**Class:** C7 (silent success is failure) — but the failure mode is new: not a producer writing
stale output, a **GUARD that stops guarding** without anyone noticing.

## The finding

`backtest/tests/test_graduated_guards.py::test_free_model_cost_estimate_is_zero` **fails in a
full-suite run and passes in isolation.**

That guard exists to protect a real, documented scar (G-PHANTOM-COST, 2026-07-01): unknown
`:free` model slugs fell through to the paid-M2 default in `_estimate_cost`, writing phantom
`cost_usd` into `minimax-calls.jsonl` and corrupting the spend summaries. A graduated guard is
the shop's mechanism for "this scar must never recur." **This one has not actually been checking
anything in full-suite runs.**

## Exact reproduction (bisected, 2 files)

```
backtest/.venv/Scripts/python.exe -m pytest \
  backtest/tests/test_eod_quant_guard.py \
  "backtest/tests/test_graduated_guards.py::test_free_model_cost_estimate_is_zero" -q
# -> 1 failed, 8 passed
```

Each file alone passes. The pollution is one-directional and ordering-dependent, and
`test_eod...` sorts before `test_graduated...`, so a default alphabetical full-suite run always
hits it.

## Mechanism — partially established, NOT fully root-caused

`backtest/tests/test_eod_quant_guard.py:24-37` installs a stub into `sys.modules` at MODULE
IMPORT time and never removes it:

```python
stub = types.ModuleType("run_minimax")
stub.call_minimax = lambda *a, **k: {...}
sys.modules["run_minimax"] = stub          # never restored
ef = _load_eod_fallback()                  # runs at import, not inside a test
```

The guard then does `importlib.import_module("run_minimax")` and gets the stub.

**What I confirmed:** the pollution source, the ordering dependence, and the two-file repro.

**What I did NOT establish, and am not claiming:** the precise final failure. The observed error
is `AttributeError: 'NoneType' object has no attribute '__dict__'` raised inside CPython's
`dataclasses.py:757` — which means something resolved to `None` during class construction, not
simply "the stub lacks `_estimate_cost`" as I first assumed. **I attempted a fix (loading
run_minimax by file path under a unique module name so a stubbed `sys.modules` entry cannot
shadow it) and it DID NOT resolve the failure — that attempt was reverted rather than left in
place.** The real mechanism is one layer deeper than sys.modules shadowing.

## Why this matters more than one red test

1. A guard that silently stops guarding is strictly worse than no guard: the scar it protects
   can recur and the suite still reports green-ish, because the failure looks like flake.
2. **There may be others.** The pattern — a test module mutating `sys.modules` at import scope,
   never restoring — would neuter any later test that imports the same name. This one was found
   by accident; nobody was looking for it.
3. It is invisible to the pre-commit safety gate, which runs a curated 6-suite subset that does
   not include this pairing. Every commit tonight passed that gate while this was broken.

## Suggested work (NOT done here — different lane, deliberately not touched)

1. Root-cause the `NoneType.__dict__` failure properly rather than at the sys.modules layer.
2. Make `test_eod_quant_guard.py` restore `sys.modules` (fixture with teardown, or
   `monkeypatch.setitem`) instead of mutating global state at import scope. Check first whether
   `eod_fallback` imports `run_minimax` lazily at call time — if so, naively deleting the stub
   could expose that lane to a real key/network call, which is why this was not done blind.
3. **Sweep for the same pattern**: `grep -rn 'sys.modules\[' backtest/tests/` and check each for
   restoration. Any unrestored entry is a candidate guard-killer.
4. Consider a suite-level conftest check that fails loudly if a test module leaves a stub in
   `sys.modules` after the session.

**Provenance:** found while running the SPY-lane regression check for the multi-symbol lane
(`1 failed, 179 passed` over 18 minutes). Not caused by the multi lane — verified by running the
multi tests together with the guard: 68 passed, no failure.
